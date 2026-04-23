import asyncio, os, httpx
from pathlib import Path
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
from .crypto import (
    derive_file_key_iv, aes_ctr_decryptor, decrypt_attributes,
    mega_chunk_boundaries, chunk_mac, combine_file_mac, file_mac_matches,
)
from .links import parse_link, FileLink, FolderLink
from .folder import enumerate_folder, build_relative_path
from .errors import (
    QuotaExceeded, GUrlExpired, RateLimited, PermanentMegaError,
    EXIT_PERMANENT, EXIT_QUOTA, EXIT_RETRY_EXHAUST,
)
from .api import MegaAPI
from .proxy import ProxyPool
from .state import load_state, save_state, pending_ranges

CHUNK = 16 * 1024 * 1024
WORKERS_DEFAULT = 8

class Downloader:
    def __init__(
        self, link_url: str, dest_dir: Path, workers: int = WORKERS_DEFAULT,
        proxies: list[str] | None = None, use_proxy_free_first: bool = True,
        verify_mac: bool = False, strict_mac: bool = False,
    ):
        self.link = parse_link(link_url)
        self.dest_dir = dest_dir
        self.workers = workers
        self.pool = ProxyPool(proxies)
        self.free_first = use_proxy_free_first
        self.verify_mac = verify_mac
        self.strict_mac = strict_mac

    async def run(self):
        limits = httpx.Limits(
            max_connections=self.workers * 2,
            max_keepalive_connections=self.workers,
        )
        async with httpx.AsyncClient(http2=True, limits=limits) as meta:
            if isinstance(self.link, FileLink):
                api = MegaAPI(meta, folder_id=None)
                info = await api.get_file_download(self.link.file_id)
                key16, nonce8, mac_seed = derive_file_key_iv(self.link.file_key_b64)
                attrs = decrypt_attributes(info["at"], key16)
                await self._download_one(
                    meta, limits, info["g"], info["s"],
                    attrs["n"], key16, nonce8, mac_seed,
                    refresh_cb=lambda: self._refresh_file(api),
                )
                return

            api = MegaAPI(meta, folder_id=self.link.folder_id)
            nodes = await enumerate_folder(api, self.link.folder_key_b64)
            files = [n for n in nodes.values() if n.type == 0]
            if self.link.sub_file_id:
                files = [n for n in files if n.handle == self.link.sub_file_id]
            if not files:
                raise PermanentMegaError(-9)
            for n in files:
                info = await api.get_node_download(n.handle)
                rel = build_relative_path(nodes, n.handle)
                out_rel = Path(rel) if rel else Path(n.name)
                await self._download_one(
                    meta, limits, info["g"], info["s"], str(out_rel),
                    n.aes_key, n.nonce, n.mac_seed,
                    refresh_cb=lambda h=n.handle: self._refresh_node(api, h),
                )

    async def _refresh_file(self, api):
        info = await api.get_file_download(self.link.file_id)
        return info["g"]

    async def _refresh_node(self, api, handle):
        info = await api.get_node_download(handle)
        return info["g"]

    async def _download_one(self, meta_client, limits, g_url, size, rel_name,
                           key16, nonce8, mac_seed, refresh_cb):
        out_path = self.dest_dir / rel_name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        state = load_state(out_path, size)
        fd = os.open(out_path, os.O_CREAT | os.O_RDWR)
        os.ftruncate(fd, size)

        queue: asyncio.Queue = asyncio.Queue()
        for s, e in pending_ranges(size, state["done"]):
            for cs, ce in self._split(s, e):
                queue.put_nowait((cs, ce))

        already = sum(e - s for s, e in state["done"])
        progress = Progress(
            "[progress.description]{task.description}",
            BarColumn(), DownloadColumn(), TransferSpeedColumn(), TimeRemainingColumn(),
        )
        with progress:
            task = progress.add_task(rel_name, total=size, completed=already)
            g_url_ref = [g_url]

            client_free = httpx.AsyncClient(http2=True, limits=limits)
            proxy_clients: dict[str, httpx.AsyncClient] = {}
            def clients_proxy(url: str) -> httpx.AsyncClient:
                if url not in proxy_clients:
                    proxy_clients[url] = httpx.AsyncClient(
                        http2=True, proxies=url, limits=limits,
                    )
                return proxy_clients[url]

            workers = [
                asyncio.create_task(
                    self._worker(i, queue, g_url_ref, fd, state, out_path,
                                progress, task, client_free, clients_proxy, refresh_cb),
                )
                for i in range(self.workers)
            ]
            try:
                await queue.join()
                for _ in workers:
                    queue.put_nowait(None)
                await asyncio.gather(*workers, return_exceptions=True)
            finally:
                os.close(fd)
                await client_free.aclose()
                for c in proxy_clients.values():
                    await c.aclose()

            if self.verify_mac and mac_seed:
                ok = self._verify_mac(out_path, size, key16, nonce8, mac_seed)
                if not ok and self.strict_mac:
                    os.unlink(out_path)
                    raise PermanentMegaError(-14)

            sp = state_path(out_path)
            if sp.exists():
                sp.unlink()
            return out_path

    def _split(self, start: int, end: int):
        for s in range(start, end, CHUNK):
            yield s, min(s + CHUNK, end)

    def _verify_mac(self, out_path: Path, size: int, key16: bytes, nonce8: bytes, mac_seed: bytes) -> bool:
        chunk_macs = []
        with open(out_path, "rb") as f:
            for off, length in mega_chunk_boundaries(size):
                f.seek(off)
                data = f.read(length)
                chunk_macs.append(chunk_mac(key16, nonce8, data))
        computed = combine_file_mac(chunk_macs, key16)
        return file_mac_matches(computed, mac_seed)

    async def _worker(self, name, queue, g_url_ref, out_fd, state, out_path,
                      progress, task_id, client_free, clients_proxy, refresh_cb):
        while True:
            rng = await queue.get()
            if rng is None:
                queue.task_done()
                return
            start, end = rng
            attempt = 0
            proxy = None
            while True:
                attempt += 1
                use_free = self.free_first and attempt <= 2
                try:
                    if use_free:
                        client = client_free
                    else:
                        proxy = self.pool.pick()
                        if proxy is None:
                            await asyncio.sleep(min(30, 2 ** attempt))
                            client = client_free
                        else:
                            client = clients_proxy(proxy.url)

                    headers = {"Range": f"bytes={start}-{end - 1}"}
                    async with client.stream(
                        "GET", g_url_ref[0], headers=headers,
                        timeout=httpx.Timeout(60, read=120),
                    ) as r:
                        if r.status_code == 403:
                            g_url_ref[0] = await refresh_cb()
                            raise RuntimeError("g-url refreshed")
                        if r.status_code == 509:
                            self.pool.release(proxy, False, 509)
                            raise RuntimeError("quota 509")
                        if r.status_code >= 400:
                            raise PermanentMegaError(r.status_code)
                        r.raise_for_status()

                        block_offset = start // 16
                        dec = aes_ctr_decryptor(key16, nonce8, block_offset)
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
                    self.pool.release(proxy, True)
                    break
                except (GUrlExpired, RuntimeError) as e:
                    self.pool.release(proxy, False)
                    if "g-url refreshed" in str(e) and attempt <= 3:
                        continue
                    if attempt > 10:
                        queue.task_done()
                        raise
                    await asyncio.sleep(min(30, 1.5 ** attempt))
                except PermanentMegaError:
                    queue.task_done()
                    raise
                except Exception as e:
                    self.pool.release(proxy, False)
                    if attempt > 10:
                        queue.task_done()
                        raise
                    await asyncio.sleep(min(30, 1.5 ** attempt))
            queue.task_done()
