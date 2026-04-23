import httpx, itertools, re, asyncio, random
from typing import Optional

API = "https://g.api.mega.co.nz/cs"
_seq = itertools.count(random.randint(0, 0xFFFFFFFF))

_LINK_RE = re.compile(
    r"mega\.nz/(?:#!|file/)([A-Za-z0-9_-]+)[!#]([A-Za-z0-9_-]+)"
)

def parse_file_link(url: str) -> tuple[str, str]:
    m = _LINK_RE.search(url)
    if not m:
        raise ValueError(f"not a MEGA file link: {url}")
    return m.group(1), m.group(2)  # file_id, file_key_b64

async def api_req(client: httpx.AsyncClient, payload: list[dict]) -> list:
    params = {"id": next(_seq)}
    r = await client.post(API, params=params, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, int):
        raise RuntimeError(f"MEGA API error: {data}")
    return data

async def get_download_info(client: httpx.AsyncClient, file_id: str) -> dict:
    """Returns {'s': size, 'at': enc_attr, 'g': cdn_url}."""
    resp = await api_req(client, [{"a": "g", "g": 1, "ssl": 2, "p": file_id}])
    item = resp[0]
    if isinstance(item, int) or "g" not in item:
        raise RuntimeError(f"could not get g-URL: {item}")
    return item