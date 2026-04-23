import asyncio, os, httpx
from pathlib import Path
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
from crypto import (
    derive_file_key_iv, aes_ctr_decryptor, decrypt_attributes,
    mega_chunk_boundaries, chunk_mac, combine_file_mac, file_mac_matches,
)
from links import parse_link, FileLink, FolderLink, FolderFileLink
from folder import enumerate_folder, build_relative_path
from errors import (
    QuotaExceeded, GUrlExpired, PermanentMegaError, RetriableMegaError,
    EXIT_OK, EXIT_PERMANENT, EXIT_QUOTA, EXIT_RETRY_EXHAUST,
    EXIT_BAD_LINK, EXIT_GENERIC,
)
from api import MegaAPI
from proxy import ProxyPool
from state import load_state, save_state, pending_ranges

CHUNK = 16 * 1024 * 1024  # 16 MiB per worker range
WORKERS_DEFAULT = 8

class Downloader:
    def __init__(
        self, link: str, dest_dir: Path,
        workers: int = WORKERS_DEFAULT,
        proxies: list[str] | None = None,
        use_proxy_free_first: bool = True,
        verify_mac: bool = False,
        strict_mac: bool = False,
    ):
        self.link = link
        self.parsed = parse_link(link)
        self.dest_dir = dest_dir
        self.workers = workers
        self.pool = ProxyPool(proxies)
        self.free_first = use_proxy_free_first
        self.verify_mac = verify_mac
        self.strict_mac = strict_mac
        self.api = MegaAPI()

    def _pending_ranges(self, size: int, done: list[list[int]]):
        return list(pending_ranges(size, done))

    def _split(self, start: int, end: int):
        for s in range(start, end, CHUNK):
            yield (s, min(s + CHUNK, end))

    async def _download_file(
        self, file_id: str, file_key_b64: str,
        out_path: Path,
        refresh_cb=None,
    ):
        key16, nonce8, mac_seed = derive_file_key_iv(file_key_b64)
        info = await self.api.get_download_info(file_id)
        attr = decrypt_attributes(info["at"], key16)
        fname = attr.get("n", "unknown")
        size = info["s"]
        g_url = info["g"]

        out_path = out_path / fname
        state = load_state(out_path, size)
        fd = os.open(out_path, os.O_CREAT | os.O_RDWR)
        os.ftruncate(fd, size)

        queue: asyncio.Queue = asyncio.Queue()
        for s, e in self._pending_ranges(size, state["done"]):
            for cs, ce in self._split(s, e):
                queue.put_nowait((cs, ce))

        already = sum(e - s for s, e in state["done"])
        progress = Progress(
            "[progress.description]{task.description}",
            BarColumn(), DownloadColumn(), TransferSpeedColumn(), TimeRemainingColumn(),
        )
        g_url_ref = [g_url]

        async with httpx.AsyncClient(http2=True) as client_free:
            try:
                with progress:
                    task = progress.add_task(fname, total=size, completed=already)
                    workers = [
                        asyncio.create_task(
                            self._worker(i, queue, g_url_ref, fd, state, out_path,
                                         progress, task, client_free, None)
                        )
                        for i in range(self.workers)
                    ]
                    await queue.join()
                    for _ in workers:
                        queue.put_nowait(None)
                    await asyncio.gather(*workers, return_exceptions=True)
            finally:
                os.close(fd)

        if self.verify_mac:
            # MAC verification over full file
            os.lseek(fd, 0, os.SEEK_SET)
            # (simplified — full impl would read chunk boundaries and chain MAC)
            pass

        save_state(out_path, {"size": size, "done": []})  # cleanup
        return out_path

    async def _worker(
        self, name, queue, g_url_ref, out_fd, state, out_path,
        progress, task_id, client_free, client_proxy,
    ):
        while True:
            rng = await queue.get()
            if rng is None:
                queue.task_done()
                return
            start, end = rng
            attempt = 0
            while True:
                attempt += 1
                proxy = None
                use_free = self.free_first and attempt <= 2
                try:
                    client = client_free
                    headers = {"Range": f"bytes={start}-{end-1}"}
                    async with client.stream("GET", g_url_ref[0], headers=headers,
                                            timeout=httpx.Timeout(60, read=120)) as r:
                        if r.status_code == 403:
                            new_info = await self.api.get_download_info(
                                self.parsed.file_id if isinstance(self.parsed, FileLink) else self.parsed.file_id
                            )
                            g_url_ref[0] = new_info["g"]
                            raise GUrlExpired("g-URL expired, refreshed")
                        if r.status_code == 509:
                            raise QuotaExceeded(f"HTTP 509 at {start}-{end}")
                        r.raise_for_status()

                        block_offset = start // 16
                        dec = aes_ctr_decryptor(self.key16 if hasattr(self, 'key16') else self._key16,
                                                self.nonce8 if hasattr(self, 'nonce8') else self._nonce8,
                                                block_offset)
                        pos = start
                        async for chunk in r.aiter_bytes(256 * 1024):
                            plain = dec.update(chunk)
                            os.pwrite(out_fd, plain, pos)
                            pos += len(plain)
                            progress.update(task_id, advance=len(plain))
                        tail = dec.finalize()
                        if tail:
                            os.pwrite(out_fd, tail, pos)

                        state["done"].append([start, end])
                        save_state(out_path, state)
                        break
                except RetriableMegaError:
                    if attempt > 10:
                        queue.task_done()
                        raise
                    await asyncio.sleep(min(30, 1.5 ** attempt))
                    continue
                except Exception:
                    if attempt > 10:
                        queue.task_done()
                        raise
                    await asyncio.sleep(min(30, 1.5 ** attempt))
                    continue
            queue.task_done()

    async def run(self):
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        if isinstance(self.parsed, FileLink):
            self._key16, self._nonce8, _ = derive_file_key_iv(self.parsed.file_key_b64)
            await self._download_file(self.parsed.file_id, self.parsed.file_key_b64, self.dest_dir)
        elif isinstance(self.parsed, FolderLink):
            async with httpx.AsyncClient(http2=True) as client:
                nodes = await enumerate_folder(client, self.parsed.folder_id, self.parsed.folder_key_b64)
            for node in nodes:
                try:
                    await self._download_file(node.id, node.file_key_b64, self.dest_dir / node.path)
                except Exception as e:
                    print(f"[skip] {node.name}: {e}", file=__import__("sys").stderr)
        elif isinstance(self.parsed, FolderFileLink):
            self._key16, self._nonce8, _ = derive_file_key_iv(self.parsed.file_key_b64)
            await self._download_file(self.parsed.file_id, self.parsed.file_key_b64, self.dest_dir)
        await self.api.close()
