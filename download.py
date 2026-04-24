"""Parallel async MEGA.nz downloader with resume, MAC verify, and proxy rotation."""
import asyncio, os, sys, httpx
from pathlib import Path
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
from crypto import (
    derive_file_key_iv, aes_ctr_decryptor, decrypt_attributes,
    mega_chunk_boundaries, chunk_mac, combine_file_mac, file_mac_matches,
)
from links import parse_link, FileLink, FolderLink, FolderFileLink
from folder import enumerate_folder, build_relative_path
from api import MegaAPI
from errors import (
    PermanentMegaError, QuotaExceeded, RateLimited,
    EXIT_OK, EXIT_PERMANENT, EXIT_QUOTA, EXIT_RETRY_EXHAUST,
    EXIT_BAD_LINK, EXIT_GENERIC,
)
from proxy import ProxyPool

CHUNK = 16 * 1024 * 1024  # 16 MiB per worker range
WORKERS_DEFAULT = 8


class Downloader:
    def __init__(self, link: str, dest_dir: Path, workers: int = WORKERS_DEFAULT,
                 proxies: list[str] | None = None, use_proxy_free_first: bool = True,
                 verify_mac: bool = False, strict_mac: bool = False,
                 refresh_cb=None):
        self.parsed = parse_link(link)
        self.key16 = self.nonce8 = self.mac_seed = None
        self.dest_dir = dest_dir
        self.workers = workers
        self.pool = ProxyPool(proxies)
        self.free_first = use_proxy_free_first
        self.verify_mac = verify_mac
        self.strict_mac = strict_mac
        self.refresh_cb = refresh_cb
        self.api = MegaAPI()

    async def _download_file(self, file_id: str, file_key_b64: str, dest_path: Path):
        key16, nonce8, mac_seed = derive_file_key_iv(file_key_b64)
        client = await self.api._get_client()
        info = await self.api.get_download_info(file_id)

        if info.get('e'):
            exc = PermanentMegaError(f"file access error: {info['e']}")
            exc.exit_code = EXIT_PERMANENT
            raise exc

        if 'g' not in info:
            raise PermanentMegaError(f"no download URL: {info}")

        size = info['s']
        g_url = info['g']
        enc_attr_b64 = info.get('at', '')
        fname = 'unknown'
        if enc_attr_b64:
            try:
                fname = decrypt_attributes(enc_attr_b64, key16).get('n', fname)
            except Exception:
                pass

        if dest_path.is_dir():
            dest_path = dest_path / fname

        self.dest_dir.mkdir(parents=True, exist_ok=True)
        state = self._load_state(dest_path, size)
        fd = os.open(dest_path, os.O_CREAT | os.O_RDWR)
        os.ftruncate(fd, size)

        completed = sum(e - s for s, e in state['done'])
        queue: asyncio.Queue = asyncio.Queue()

        for s, e in self._pending_ranges(size, state['done']):
            for cs, ce in self._split(s, e):
                queue.put_nowait((cs, ce))

        progress = Progress(
            "[progress.description]{task.description}",
            BarColumn(), DownloadColumn(), TransferSpeedColumn(), TimeRemainingColumn(),
        )
        with progress:
            task = progress.add_task(fname, total=size, completed=completed)
            g_ref = [g_url]

            async def worker(q: asyncio.Queue):
                while True:
                    rng = await q.get()
                    if rng is None:
                        q.task_done()
                        return
                    start, end = rng
                    attempt = 0
                    while True:
                        attempt += 1
                        proxy = None
                        use_free = self.free_first and attempt <= 2
                        try:
                            if use_free:
                                c = client
                            else:
                                proxy = self.pool.pick()
                                if proxy is None:
                                    await asyncio.sleep(min(30, 2 ** attempt))
                                    c = client
                                else:
                                    c = await self._proxy_client(proxy.url)

                            headers = {"Range": f"bytes={start}-{end-1}"}
                            async with c.stream("GET", g_ref[0], headers=headers,
                                               timeout=httpx.Timeout(60, read=120)) as r:
                                if r.status_code == 403:
                                    new_info = await self.api.get_download_info(file_id)
                                    g_ref[0] = new_info['g']
                                    if self.refresh_cb:
                                        self.refresh_cb(g_ref[0])
                                    raise RuntimeError("g-url refreshed")
                                if r.status_code == 509:
                                    self.pool.release(proxy, False, 509)
                                    raise RuntimeError("quota 509")

                                r.raise_for_status()

                                block_offset = start // 16
                                dec = aes_ctr_decryptor(key16, nonce8, block_offset)
                                pos = start
                                async for chunk in r.aiter_bytes(256 * 1024):
                                    plain = dec.update(chunk)
                                    os.pwrite(fd, plain, pos)
                                    pos += len(plain)
                                    progress.update(task, advance=len(plain))
                                tail = dec.finalize()
                                if tail:
                                    os.pwrite(fd, tail, pos)

                                state["done"].append([start, end])
                                self._save_state(dest_path, state)
                                self.pool.release(proxy, True)
                                break
                        except Exception as e:
                            self.pool.release(proxy, False)
                            if attempt > 10:
                                q.task_done()
                                exc = type(e)()
                                exc.exit_code = EXIT_RETRY_EXHAUST
                                raise
                            await asyncio.sleep(min(30, 1.5 ** attempt))
                    q.task_done()

            client_free = httpx.AsyncClient(http2=True)
            proxy_clients = {}

            async def _proxy_client(url: str) -> httpx.AsyncClient:
                if url not in proxy_clients:
                    proxy_clients[url] = httpx.AsyncClient(http2=True, proxies=url)
                return proxy_clients[url]

            workers = [asyncio.create_task(worker(queue)) for _ in range(self.workers)]
            await queue.join()
            for _ in workers:
                queue.put_nowait(None)
            await asyncio.gather(*workers, return_exceptions=True)
            await client_free.aclose()
            for c in proxy_clients.values():
                await c.aclose()

        os.close(fd)

        if self.verify_mac:
            fd2 = os.open(dest_path, os.O_RDONLY)
            computed = combine_file_mac(
                chunk_mac(dest_path, fd2, mac_seed, size)
            )
            os.close(fd2)
            mac = info.get('mac', '')
            if mac:
                expected = bytes(int(x) for x in mac.split(',')[:2]) if ',' in mac else b''
                if not file_mac_matches(computed, expected):
                    dest_path.unlink()
                    raise PermanentMegaError("MAC verification failed — file corrupted or tampered with")

        sp = self._state_path(dest_path)
        if sp.exists():
            sp.unlink()

        return dest_path

    async def run(self):
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        if isinstance(self.parsed, FileLink):
            self._key16, self._nonce8, _ = derive_file_key_iv(self.parsed.file_key_b64)
            await self._download_file(self.parsed.file_id, self.parsed.file_key_b64, self.dest_dir)
        elif isinstance(self.parsed, FolderLink):
            async with httpx.AsyncClient(http2=True) as client:
                nodes = await enumerate_folder(client, self.parsed.folder_id, self.parsed.folder_key_b64)
            if not nodes:
                print("[bad-link] Folder returned no files (link may be empty, deleted, or the key is incorrect)", file=sys.stderr)
                sys.exit(EXIT_BAD_LINK)
            for node in nodes:
                try:
                    await self._download_file(node.id, node.file_key_b64, self.dest_dir / node.path)
                except Exception as e:
                    print(f"[skip] {node.name}: {e}", file=sys.stderr)
        elif isinstance(self.parsed, FolderFileLink):
            self._key16, self._nonce8, _ = derive_file_key_iv(self.parsed.file_key_b64)
            await self._download_file(self.parsed.file_id, self.parsed.file_key_b64, self.dest_dir)
        await self.api.close()

    def _state_path(self, out_path: Path) -> Path:
        return out_path.with_suffix(out_path.suffix + ".megapull.json")

    def _load_state(self, out_path: Path, size: int) -> dict:
        sp = self._state_path(out_path)
        if sp.exists():
            st = __import__('json').loads(sp.read_text())
            if st.get("size") == size:
                return st
        return {"size": size, "done": []}

    def _save_state(self, out_path: Path, state: dict):
        self._state_path(out_path).write_text(__import__('json').dumps(state))

    def _pending_ranges(self, size: int, done: list[list[int]]):
        done = sorted(done)
        cur = 0
        for s, e in done:
            if s > cur:
                yield (cur, s)
            cur = max(cur, e)
        if cur < size:
            yield (cur, size)

    def _split(self, start: int, end: int):
        for s in range(start, end, CHUNK):
            yield (s, min(s + CHUNK, end))