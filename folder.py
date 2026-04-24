from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from crypto import folder_master_key, decrypt_node_key, fold_file_nodekey, decrypt_attributes, b64url_decode

@dataclass
class FolderNode:
    handle: str
    name: str
    size: int
    file_key_b64: str
    decrypted_key_32: bytes

def parse_folder_response(nodes_resp: list, master_key_b64: str) -> list[FolderNode]:
    """Parse a=f response into FolderNode list. The 'k' field is encrypted with the folder key."""
    master = folder_master_key(master_key_b64)
    result = []
    for node in nodes_resp:
        t = node.get("t", 0)
        if t == 1:
            continue  # skip subfolders
        h = node.get("h", "")
        s = node.get("s", 0)
        a = node.get("a", "")
        k_enc = node.get("k", "")
        if not h or not k_enc:
            continue
        # k is "handle:encrypted_key" — encrypted with folder master key
        if ":" in k_enc:
            _, enc_b64 = k_enc.split(":", 1)
        else:
            enc_b64 = k_enc
        dec = decrypt_node_key(enc_b64, master)  # 32-byte file node key
        from crypto import b64url_encode
        file_key_b64 = b64url_encode(dec)
        name = "(unknown)"
        if a:
            try:
                attrs = decrypt_attributes(a, dec[:16])
                name = attrs.get("n", name)
            except Exception:
                pass
        result.append(FolderNode(handle=h, name=name, size=s, file_key_b64=file_key_b64, decrypted_key_32=dec))
    return result