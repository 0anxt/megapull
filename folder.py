from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import asyncio
from crypto import (
    folder_master_key, decrypt_node_key, b64url_decode, b64url_encode,
    bytes_to_a32, a32_to_bytes, derive_file_key_iv,
)
from errors import MegaError

@dataclass
class FolderNode:
    id: str
    name: str
    size: int
    file_key_b64: str
    path: str

async def enumerate_folder(client, folder_id: str, folder_key_b64: str) -> list[FolderNode]:
    master = folder_master_key(folder_key_b64)
    from api import api_req
    payload = [{"a": "f", "n": folder_id, "r": 1, "c": 1}]
    resp = await api_req(client, payload)
    raw_nodes = []
    if isinstance(resp[0], dict):
        raw_nodes = resp[0].get("f", [])
    elif isinstance(resp, list) and len(resp) > 1:
        raw_nodes = resp[1].get("f", []) if isinstance(resp[1], dict) else []

    nodes = []
    for node in raw_nodes:
        if node.get("t") == 1:
            continue
        raw_key = node.get("k", "")
        if not raw_key:
            continue
        dec_key = decrypt_node_key(raw_key, master)
        from crypto import fold_file_nodekey
        file_key_b64 = b64url_encode(dec_key)
        name = node.get("a") or node.get("n") or node.get("h", "unknown")
        size = node.get("s", 0)
        node_id = node.get("h", "")
        nodes.append(FolderNode(
            id=node_id,
            name=name,
            size=size,
            file_key_b64=file_key_b64,
            path=name,
        ))
    return nodes

def build_relative_path(nodes: list[FolderNode], node_id: str) -> str:
    for n in nodes:
        if n.id == node_id:
            return n.path
    return node_id
