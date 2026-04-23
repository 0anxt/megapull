import asyncio, os, httpx
from pathlib import Path
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
from .crypto import derive_file_key_iv, aes_ctr_decryptor, decrypt_attributes
from .api import parse_file_link, get_download_info
from .proxy import ProxyPool
from .state import load_state, save_state, pending_ranges

CHUNK = 16 * 1024 * 1024  # 16 MiB per worker range
WORKERS_DEFAULT = 8


class Downloader:
    def __init__(self, link: str, dest_dir: Path, workers: int = WORKERS_DEFAULT,
                 proxies: list[str] | None = None, use_proxy_free_first: bool = True):
        self.file_id, self.key_b64 = parse_file_link(link)
        self.key16, self.nonce8, _ = derive_file_key_iv(self.key_b64)
        self.dest_dir = dest_dir
        self.workers = workers
        self.pool = ProxyPool(proxies)
        self.free_first = use_proxy_free_first

    async def _fetch_g(self, client):
        info = await get_download_info(client, self.file_id)
        attr = decrypt_attributes(info["at"], self.key16)
        return info["g"], info["s"], attr["n"]

    def _split(self, start: int, end: int):
        for s in range(start, end, CHUNK):
            yield (s, min(s + CHUNK, end))

    async def _worker(self, name, queue, g_url_ref, out_fd, state, out_path,
                     progress, task_id, client_free, clients_proxy):
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
                    if use_free:
                        client = client_free
                    else:
                        proxy = self.pool.pick()
                        if proxy is None:
                            await asyncio.sleep(min(30, 2 ** attempt))
                            client = client_free
                        else:
                            client = clients_proxy(proxy.url)

                    headers = {"Range": f"bytes={start}-{end-1}"}
                    async with client.stream("GET", g_url_ref[0], headers=headers,
                                            timeout=httpx.Timeout(60, read=120)) as r:
                        if r.status_code == 403:
                            async with httpx.AsyncClient(http2=True) as refresh:
                                new = await get_download_info(refresh, self.file_id)
                            g_url_ref[0] = new["g"]
                            raise RuntimeError("g-url refreshed")
                        if r.status_code == 509:
                            self.pool.release(proxy, False, 509)
                            raise RuntimeError("quota 509")
                        r.raise_for_status()

                        block_offset = start // 16
                        dec = aes_ctr_decryptor(self.key16, self.nonce8, block_offset)
                        pos = start
                        async for chunk in r.aiter_bytes(1024 * 256):
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
                except Exception as e:
                    self.pool.release(proxy, False)
                    if attempt > 10:
                        queue.task_done()
                        raise
                    await asyncio.sleep(min(30, 1.5 ** attempt))
            queue.task_done()

    async def run(self):
        limits = httpx.Limits(max_connections=self.workers * 2, max_keepalive_connections=self.workers)
        async with httpx.AsyncClient(http2=True, limits=limits) as client_meta:
            g_url, size, fname = await self._fetch_g(client_meta)
        out_path = self.dest_dir / fname
        self.dest_dir.mkdir(parents=True, exist_ok=True)

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
            task = progress.add_task(fname, total=size, completed=already)
            g_url_ref = [g_url]

            client_free = httpx.AsyncClient(http2=True, limits=limits)
            proxy_clients: dict[str, httpx.AsyncClient] = {}
            def clients_proxy(url: str) -> httpx.AsyncClient:
                if url not in proxy_clients:
                    proxy_clients[url] = httpx.AsyncClient(http2=True, proxies=url,
                                                          limits=limits)
                return proxy_clients[url]

            try:
                workers = [asyncio.create_task(
                    self._worker(i, queue, g_url_ref, fd, state, out_path,
                                 progress, task, client_free, clients_proxy))
                           for i in range(self.workers)]
                await queue.join()
                for _ in workers:
                    queue.put_nowait(None)
                await asyncio.gather(*workers, return_exceptions=True)
            finally:
                os.close(fd)
                await client_free.aclose()
                for c in proxy_clients.values():
                    await c.aclose()

        sp = out_path.with_suffix(out_path.suffix + ".megapull.json")
        if sp.exists():
            sp.unlink()
        return out_path