from __future__ import annotations
import base64, struct, json
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

def b64url_decode(s: str) -> bytes:
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)

def b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")

def bytes_to_a32(b: bytes) -> list[int]:
    if len(b) % 4:
        b += b"\x00" * (4 - len(b) % 4)
    return list(struct.unpack(f">{len(b)//4}I", b))

def a32_to_bytes(a: list[int]) -> bytes:
    return struct.pack(f">{len(a)}I", *a)

def derive_file_key_iv(file_key_b64: str):
    raw = b64url_decode(file_key_b64)
    a = bytes_to_a32(raw)
    if len(a) != 8:
        raise ValueError("bad file key length")
    key = [a[0] ^ a[4], a[1] ^ a[5], a[2] ^ a[6], a[3] ^ a[7]]
    iv = a[4:6]
    mac = a[6:8]
    return a32_to_bytes(key), a32_to_bytes(iv), a32_to_bytes(mac)

def aes_ctr_decryptor(key16: bytes, nonce8: bytes, start_block: int = 0):
    iv = nonce8 + start_block.to_bytes(8, "big")
    return Cipher(algorithms.AES(key16), modes.CTR(iv), default_backend()).decryptor()

def decrypt_attributes(enc_b64: str, key16: bytes) -> dict:
    data = b64url_decode(enc_b64)
    dec = Cipher(algorithms.AES(key16), modes.CBC(b"\x00" * 16), default_backend()).decryptor()
    out = dec.update(data) + dec.finalize()
    if not out.startswith(b"MEGA"):
        raise ValueError("attr decrypt failed")
    return json.loads(out[4:].rstrip(b"\x00").decode())

# --- Folder-specific crypto ---

def folder_master_key(folder_key_b64: str) -> bytes:
    raw = b64url_decode(folder_key_b64)
    a = bytes_to_a32(raw)
    return a32_to_bytes(a)

def decrypt_node_key(enc_node_key_b64: str, master_key: bytes) -> bytes:
    data = b64url_decode(enc_node_key_b64)
    dec = Cipher(algorithms.AES(master_key), modes.ECB(), default_backend()).decryptor()
    return dec.update(data) + dec.finalize()

def fold_file_nodekey(file_key_b64: str) -> bytes:
    """Decrypt a file key stored inside a folder node (AES-ECB)."""
    raw = b64url_decode(file_key_b64)
    if len(raw) != 32:
        raise ValueError("expecting 32-byte encrypted file key")
    a = bytes_to_a32(raw[:16])  # first 4 u32s are the encrypted key
    dec = Cipher(algorithms.AES(raw[16:32]), modes.ECB(), default_backend()).decryptor()
    return dec.update(raw[:16]) + dec.finalize()

# --- Chunk MAC (MEGA CBC-MAC per chunk boundary) ---

def _cbc_mac_chunk(key: bytes, data: bytes) -> bytes:
    if len(data) % 16:
        data += b"\x00" * (16 - len(data) % 16)
    dec = Cipher(algorithms.AES(key), modes.CBC(data[:16]), default_backend()).decryptor()
    out = dec.update(data[16:])
    return dec.finalize() if not out else out

def mega_chunk_boundaries(file_size: int) -> list[int]:
    boundaries = []
    next_boundary = 128 * 1024
    pos = 0
    while pos < file_size:
        boundaries.append(pos)
        if next_boundary <= file_size:
            boundaries.append(next_boundary)
            pos = next_boundary
            next_boundary = min(next_boundary * 2, file_size)
        else:
            boundaries.append(file_size)
            break
    return sorted(set(boundaries))

def chunk_mac(data: bytes, mac_key: bytes) -> list[int]:
    a = [0, 0, 0, 0]
    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        if len(chunk) < 16:
            chunk = chunk + b"\x00" * (16 - len(chunk))
        for j in range(4):
            a[j] ^= struct.unpack(">I", chunk[j * 4 : j * 4 + 4])[0]
        dec = Cipher(algorithms.AES(mac_key), modes.ECB(), default_backend()).decryptor()
        a = list(struct.unpack(">4I", dec.update(struct.pack(">4I", *a)) + dec.finalize()))
    return a

def combine_file_mac(macs: list[list[int]]) -> list[int]:
    combined = [0, 0, 0, 0]
    for mac in macs:
        for i in range(4):
            combined[i] ^= mac[i]
    return combined

def file_mac_matches(file_mac: list[int], expected: list[int]) -> bool:
    return file_mac == expected
