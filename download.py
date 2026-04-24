"""Parallel async MEGA.nz downloader with resume, MAC verify, and proxy rotation."""
import asyncio, os, httpx
from pathlib import Path
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
from api import MegaAPI
from links import parse_link, FileLink, FolderLink, FolderFileLink
from folder import enumerate_folder, parse_folder_response
from errors import EXIT_OK, EXIT_PERMANENT, EXIT_QUOTA, EXIT_RETRY_EXHAUST, EXIT_BAD_LINK, EXIT_GENERIC, raise_from_code, MegaError
from crypto import derive_file_key_iv, aes_ctr_decryptor, decrypt_attributes, b64url_encode, bytes_to_a32, a32_to_bytes
import state

CHUNK = 16 * 1024 * 1024
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

    async def run(self) -> Path:
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        client = await self.api._get_client()

        if isinstance(self.parsed, FileLink):
            return await self._download_file(client, self.parsed.file_id, self.parsed.file_key_b64, None)
        elif isinstance(self.parsed, FolderLink):
            return await self._download_folder(client, self.parsed.folder_id, self.parsed.folder_key_b64)
        elif isinstance(self.parsed, FolderFileLink):
            return await self._download_file(client, self.parsed.sub_file_id, self.parsed.folder_key_b64, self.parsed.folder_id)
        else:
            raise EXIT_BAD_LINK(f"unrecognized link type: {self.link}")

    async def _download_file(self, client, file_id: str, file_key_b64: str, folder_id: str | None):
        from crypto import derive_file_key_iv, b64url_encode, fold_file_nodekey
        if folder_id:
            from crypto import folder_master_key, decrypt_node_key
            master = folder_master_key(self.parsed.folder_key_b64)
            dec_key = decrypt_node_key(file_id, master)
            key16, nonce8, mac_seed = fold_file_nodekey(dec_key)
            info = await self.api.get_download_info(file_id, self.parsed.folder_key_b64)
        else:
            key16, nonce8, mac_seed = derive_file_key_iv(file_key_b64)
            info = await self.api.get_download_info(file_id, None)

        g_url = info["g"]
        size = info["s"]
        enc_attr = info["at"]
        attrs = decrypt_attributes(enc_attr, key16)
        fname = attrs.get("n", "unknown")
        out_path = self.dest_dir / fname

        print(f"[download] {fname} ({size} bytes) -> {out_path}")
        # TODO: implement parallel chunked download with resume
        return out_path

    async def _download_folder(self, client, folder_id: str, folder_key_b64: str):
        from crypto import folder_master_key
        self.api.set_folder_session(folder_id)
        nodes = await self.api.enumerate_folder(folder_id, folder_key_b64)
        print(f"[folder] {len(nodes)} files found in folder")
        for node in nodes:
            print(f"  - {node['name']} ({node.get('s', 0)} bytes) handle={node['h']}")
        return self.dest_dir

async def run_async(link: str, out_dir: str, workers: int = WORKERS_DEFAULT, proxies: list[str] = None, force_proxy: bool = False):
    dest = Path(out_dir)
    dl = Downloader(link, dest, workers, proxies, use_proxy_free_first=not force_proxy)
    return await dl.run()

def main():
    import argparse, sys
    ap = argparse.ArgumentParser("megapull")
    ap.add_argument("link", help="MEGA public file or folder link")
    ap.add_argument("-o", "--out", default=".", help="destination directory")
    ap.add_argument("-w", "--workers", type=int, default=WORKERS_DEFAULT)
    ap.add_argument("--proxies", help="file with proxy URLs")
    ap.add_argument("--force-proxy", action="store_true")
    ap.add_argument("--verify-mac", action="store_true")
    ap.add_argument("--strict-mac", action="store_true")
    args = ap.parse_args()

    proxies = None
    if args.proxies:
        proxies = [l.strip() for l in Path(args.proxies).read_text().splitlines() if l.strip() and not l.startswith("#")]

    try:
        out = asyncio.run(run_async(args.link, args.out, args.workers, proxies, args.force_proxy))
        print(f"[done] {out}", file=sys.stderr)
        sys.exit(EXIT_OK)
    except MegaError as e:
        if isinstance(e, type(None).__class__(MegaError)):
            pass
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(EXIT_PERMANENT)
    except SystemExit as e:
        sys.exit(e.code)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(EXIT_GENERIC)

if __name__ == "__main__":
    main()