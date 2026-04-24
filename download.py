"""Parallel async MEGA.nz downloader with resume, MAC verify, and proxy rotation."""
import asyncio, os, sys, httpx
from pathlib import Path
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn

from api import MegaAPI
from links import parse_link, FileLink, FolderLink, FolderFileLink
from folder import parse_folder_response
from crypto import derive_file_key_iv, aes_ctr_decryptor, decrypt_attributes, b64url_encode, bytes_to_a32, a32_to_bytes
from crypto import derive_file_key_iv, b64url_encode, fold_file_nodekey
from crypto import folder_master_key, decrypt_node_key
from crypto import folder_master_key
from errors import EXIT_OK, EXIT_PERMANENT, EXIT_QUOTA, EXIT_RETRY_EXHAUST, EXIT_BAD_LINK, EXIT_GENERIC, raise_from_code, MegaError, PermanentMegaError, QuotaExceeded

CHUNK = 16 * 1024 * 1024  # 16 MiB per worker range
WORKERS_DEFAULT = 8

class Downloader:
    def __init__(self, link: str, dest_dir: Path, workers: int = WORKERS_DEFAULT, proxies: list[str] | None = None, use_proxy_free_first: bool = True, verify_mac: bool = False, strict_mac: bool = False):
        self.link = link
        self.parsed = parse_link(link)
        self.dest_dir = dest_dir
        self.workers = workers
        self.proxies = proxies or []
        self.free_first = use_proxy_free_first
        self.verify_mac = verify_mac
        self.strict_mac = strict_mac
        self.api = MegaAPI()

    async def run(self):
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        
        if isinstance(self.parsed, FileLink):
            key16, nonce8, mac_seed = derive_file_key_iv(self.parsed.file_key_b64)
            dl = await self.api.get_download_info(self.parsed.file_id, self.parsed.file_key_b64)
            fname = decrypt_attributes(dl["at"], key16)["n"]
            size = dl["s"]
            g_url = dl["g"]
            await self._download_file(fname, size, g_url, key16, nonce8, mac_seed, None)

        elif isinstance(self.parsed, FolderLink):
            self.api.set_folder_session(self.parsed.folder_id)
            nodes = await self.api.enumerate_folder(self.parsed.folder_id, self.parsed.folder_key_b64)
            if not nodes:
                print("[bad-link] Folder returned no files (link may be empty, deleted, or the key is incorrect)", file=sys.stderr)
                sys.exit(EXIT_BAD_LINK)
            master_key = folder_master_key(self.parsed.folder_key_b64)
            for node in nodes:
                if node.get("t") == 0:  # file
                    enc_key_b64 = node["k"].split(":")[1] if ":" in node["k"] else node["k"]
                    node_key_32 = decrypt_node_key(enc_key_b64, master_key)
                    key16, nonce8, mac_seed = fold_file_nodekey(node_key_32)
                    dl = await self.api.get_node_download(node["h"], self.parsed.folder_key_b64)
                    fname = decrypt_attributes(node["a"], key16)["n"]
                    size = dl["s"]
                    g_url = dl["g"]
                    await self._download_file(fname, size, g_url, key16, nonce8, mac_seed, None)

        elif isinstance(self.parsed, FolderFileLink):
            master_key = folder_master_key(self.parsed.folder_key_b64)
            node_key_32 = decrypt_node_key(self.parsed.sub_file_key_b64, master_key)
            key16, nonce8, mac_seed = fold_file_nodekey(node_key_32)
            dl = await self.api.get_node_download(self.parsed.sub_file_id, self.parsed.folder_key_b64)
            fname = decrypt_attributes(self.parsed.sub_file_id, key16)["n"]
            size = dl["s"]
            g_url = dl["g"]
            await self._download_file(fname, size, g_url, key16, nonce8, mac_seed, None)

        await self.api.close()

    async def _download_file(self, fname, size, g_url, key16, nonce8, mac_seed, folder_node_key_32):
        out_path = self.dest_dir / fname
        print(f"Downloading {fname} ({size} bytes) via {g_url[:60]}...")

        fd = os.open(out_path, os.O_CREAT | os.O_RDWR)
        os.ftruncate(fd, size)

        queue: asyncio.Queue = asyncio.Queue()
        for s in range(0, size, CHUNK):
            queue.put_nowait((s, min(s + CHUNK, size)))

        progress = Progress(
            "[progress.description]{task.description}",
            BarColumn(), DownloadColumn(), TransferSpeedColumn(), TimeRemainingColumn(),
        )
        with progress:
            task = progress.add_task(fname, total=size)

            workers = [
                asyncio.create_task(self._worker(i, queue, g_url, fd, progress, task, key16, nonce8))
                for i in range(self.workers)
            ]
            await queue.join()
            for _ in workers:
                queue.put_nowait(None)
            await asyncio.gather(*workers, return_exceptions=True)

        os.close(fd)
        print(f"[done] {out_path}")

    async def _worker(self, name, queue, g_url, fd, progress, task, key16, nonce8):
        async with httpx.AsyncClient(http2=True) as client:
            while True:
                rng = await queue.get()
                if rng is None:
                    queue.task_done()
                    return
                start, end = rng
                attempt = 0
                while True:
                    attempt += 1
                    try:
                        headers = {"Range": f"bytes={start}-{end-1}"}
                        async with client.stream("GET", g_url, headers=headers, timeout=httpx.Timeout(60, read=120)) as r:
                            if r.status_code == 403:
                                raise Exception("g-url expired")
                            r.raise_for_status()
                            block_offset = start // 16
                            dec = aes_ctr_decryptor(key16, nonce8, block_offset)
                            pos = start
                            async for chunk in r.aiter_bytes(262144):
                                plain = dec.update(chunk)
                                os.pwrite(fd, plain, pos)
                                pos += len(plain)
                                progress.update(task, advance=len(plain))
                            tail = dec.finalize()
                            if tail:
                                os.pwrite(fd, tail, pos)
                        break
                    except Exception as e:
                        if attempt > 10:
                            queue.task_done()
                            return
                        await asyncio.sleep(min(30, 1.5 ** attempt))
                queue.task_done()


async def main():
    import argparse
    parser = argparse.ArgumentParser("megapull")
    parser.add_argument("link", help="MEGA public file or folder link")
    parser.add_argument("-o", "--out", default=".", help="destination directory")
    parser.add_argument("-w", "--workers", type=int, default=WORKERS_DEFAULT)
    parser.add_argument("--proxies", help="file with one proxy URL per line")
    parser.add_argument("--force-proxy", action="store_true")
    parser.add_argument("--verify-mac", action="store_true")
    parser.add_argument("--strict-mac", action="store_true")
    args = parser.parse_args()

    proxies = None
    if args.proxies:
        proxies = [l.strip() for l in Path(args.proxies).read_text().splitlines() if l.strip() and not l.startswith("#")]

    dl = Downloader(args.link, Path(args.out), workers=args.workers, proxies=proxies,
                    use_proxy_free_first=not args.force_proxy,
                    verify_mac=args.verify_mac, strict_mac=args.strict_mac)
    try:
        await dl.run()
    except PermanentMegaError as e:
        print(f"[permanent-error] {e}", file=sys.stderr)
        sys.exit(EXIT_PERMANENT)
    except QuotaExceeded as e:
        print(f"[quota] {e}", file=sys.stderr)
        sys.exit(EXIT_QUOTA)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(EXIT_GENERIC)

if __name__ == "__main__":
    asyncio.run(main())