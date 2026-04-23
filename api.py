from __future__ import annotations
import httpx, itertools, random, asyncio
from typing import Optional
from errors import raise_from_code, MegaError, RetriableMegaError, QuotaExceeded, GUrlExpired

API = "https://g.api.mega.co.nz/cs"
_seq = itertools.count(random.randint(0, 0xFFFFFFFF))

async def api_req(client: httpx.AsyncClient, payload: list[dict]) -> list:
    params = {"id": next(_seq)}
    r = await client.post(API, params=params, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, int):
        raise_from_code(data)
    return data

async def get_download_info(client: httpx.AsyncClient, file_id: str, folder_key_b64: str | None = None) -> dict:
    if folder_key_b64:
        from crypto import folder_master_key, decrypt_node_key, fold_file_nodekey
        master = folder_master_key(folder_key_b64)
        dec_key = decrypt_node_key(file_id, master)
        file_key_b64 = crypto.b64url_encode(dec_key)
        payload = [{"a": "g", "g": 1, "ssl": 2, "n": file_id, "k": file_key_b64}]
    else:
        payload = [{"a": "g", "g": 1, "ssl": 2, "p": file_id}]
    resp = await api_req(client, payload)
    item = resp[0]
    if isinstance(item, int) or "g" not in item:
        raise MegaError(f"could not get g-URL: {item}")
    return item

async def enumerate_folder(client: httpx.AsyncClient, folder_id: str, folder_key_b64: str) -> list[dict]:
    from crypto import folder_master_key, decrypt_node_key
    master = folder_master_key(folder_key_b64)
    payload = [{"a": "f", "n": folder_id, "r": 1, "c": 1}]
    resp = await api_req(client, payload)
    nodes = resp[0].get("f", []) if isinstance(resp[0], dict) else []
    result = []
    for node in nodes:
        if node.get("t") == 1:  # folder node
            continue
        enc_k = node.get("k", "")
        if enc_k:
            dec_k = decrypt_node_key(enc_k, master)
            node["_dec_key"] = dec_k
        result.append(node)
    return result

class MegaAPI:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._seq = itertools.count(random.randint(0, 0xFFFFFFFF))

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(http2=True)
        return self._client

    async def api(self, payload: list[dict]) -> list:
        c = await self._get_client()
        params = {"id": next(self._seq)}
        r = await c.post(API, params=params, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, int):
            raise_from_code(data)
        return data

    async def get_download_info(self, file_id: str, folder_key_b64: str | None = None) -> dict:
        return await get_download_info(await self._get_client(), file_id, folder_key_b64)

    async def enumerate_folder(self, folder_id: str, folder_key_b64: str) -> list[dict]:
        return await enumerate_folder(await self._get_client(), folder_id, folder_key_b64)

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
