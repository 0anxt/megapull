from __future__ import annotations
import httpx, itertools, random, asyncio
from typing import Optional
from .errors import (
    MegaError, PermanentMegaError, RateLimited,
    QuotaExceeded, GUrlExpired, raise_for_code,
)

API = "https://g.api.mega.co.nz/cs"
_seq = itertools.count(random.randint(0, 0xFFFFFFFF))

class MegaAPI:
    def __init__(self, client: httpx.AsyncClient, folder_id: str | None = None):
        self.client = client
        self.folder_id = folder_id

    async def req(self, payload: list[dict], *, max_attempts: int = 6) -> list:
        params = {"id": next(_seq)}
        if self.folder_id:
            params["n"] = self.folder_id
        attempt = 0
        while True:
            attempt += 1
            try:
                r = await self.client.post(API, params=params, json=payload, timeout=30)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
                if attempt >= max_attempts:
                    raise
                await asyncio.sleep(min(30, 1.5 ** attempt))
                continue

            if r.status_code in (429, 500, 503, 509):
                if attempt >= max_attempts:
                    raise RateLimited(r.status_code, r.text)
                await asyncio.sleep(min(60, (1.8 ** attempt) + random.random()))
                continue
            if r.status_code >= 400:
                body = r.text.strip()
                if body.lstrip("-").isdigit():
                    code = int(body)
                    try:
                        raise_for_code(code)
                    except PermanentMegaError:
                        raise
                if attempt >= max_attempts:
                    raise MegaError(r.status_code)
                await asyncio.sleep(min(30, 1.5 ** attempt))
                continue
            r.raise_for_status()

            data = r.json()
            if isinstance(data, int):
                try:
                    raise_for_code(data)
                except PermanentMegaError:
                    raise
                if attempt >= max_attempts:
                    raise MegaError(data)
                await asyncio.sleep(min(30, 1.5 ** attempt))
                continue
            return data

    async def get_file_download(self, file_id: str) -> dict:
        assert self.folder_id is None
        resp = await self.req([{"a": "g", "g": 1, "ssl": 2, "p": file_id}])
        item = resp[0]
        if isinstance(item, int):
            raise_for_code(item)
        return item

    async def get_folder_nodes(self) -> dict:
        assert self.folder_id
        resp = await self.req([{"a": "f", "c": 1, "r": 1, "ca": 1}])
        item = resp[0]
        if isinstance(item, int):
            raise_for_code(item)
        return item

    async def get_node_download(self, node_handle: str) -> dict:
        assert self.folder_id
        resp = await self.req([{"a": "g", "g": 1, "ssl": 2, "n": node_handle}])
        item = resp[0]
        if isinstance(item, int):
            raise_for_code(item)
        return item
