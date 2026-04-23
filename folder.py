from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .crypto import (
    folder_master_key, decrypt_node_key, fold_file_nodekey,
    decrypt_attributes, b64url_decode,
)

@dataclass
class FolderNode:
    handle: str
    parent: str
    type: int
    name: str
    size: int
    aes_key: Optional[bytes] = None
    nonce: Optional[bytes] = None
    mac_seed: Optional[bytes] = None
    dir_key: Optional[bytes] = None

def _parse_shared_key(k_field: str) -> str:
    return k_field.split("/")[0].split(":")[1]

async def enumerate_folder(api, folder_key_b64: str) -> dict[str, FolderNode]:
    master = folder_master_key(folder_key_b64)
    listing = await api.get_folder_nodes()
    nodes: dict[str, FolderNode] = {}

    raw = listing["f"]
    for f in raw:
        h = f["h"]
        t = f["t"]
        if t == 2:
            nodes[h] = FolderNode(handle=h, parent="", type=2, name="", size=0, dir_key=master)

    for pass_t in (1, 0):
        for f in raw:
            if f.get("t") != pass_t:
                continue
            h = f["h"]
            parent = f.get("p", "")
            try:
                enc_b64 = _parse_shared_key(f["k"])
            except (KeyError, IndexError, ValueError):
                continue
            try:
                nk = decrypt_node_key(enc_b64, master)
            except Exception:
                continue
            if pass_t == 1:
                name = "?"
                try:
                    name = decrypt_attributes(f["a"], nk).get("n", h)
                except Exception:
                    pass
                nodes[h] = FolderNode(handle=h, parent=parent, type=1, name=name, size=0, dir_key=nk)
            else:
                aes_key, nonce, mac_seed = fold_file_nodekey(nk)
                name = "?"
                try:
                    name = decrypt_attributes(f["a"], aes_key).get("n", h)
                except Exception:
                    pass
                nodes[h] = FolderNode(
                    handle=h, parent=parent, type=0,
                    name=name, size=int(f.get("s", 0)),
                    aes_key=aes_key, nonce=nonce, mac_seed=mac_seed,
                )
    return nodes

def build_relative_path(nodes: dict[str, FolderNode], handle: str) -> str:
    parts = []
    cur = nodes.get(handle)
    while cur and cur.type != 2:
        parts.append(cur.name or cur.handle)
        cur = nodes.get(cur.parent)
    return "/".join(reversed(parts))
