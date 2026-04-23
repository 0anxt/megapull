from __future__ import annotations
import base64, struct, json
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

def b64url_decode(s: str) -> bytes:
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode())

def b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")

def bytes_to_a32(b: bytes) -> list[int]:
    if len(b) % 4:
        b += b"\x00" * (4 - len(b) % 4)
    return list(struct.unpack(f">{len(b)//4}I", b))

def a32_to_bytes(a: list[int]) -> bytes:
    return struct.pack(f">{len(a)}I", *a)

def derive_file_key_iv(file_key_b64: str) -> tuple[bytes, bytes, bytes]:
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

def aes_ecb_decrypt(key16: bytes, data: bytes) -> bytes:
    dec = Cipher(algorithms.AES(key16), modes.ECB(), default_backend()).decryptor()
    return dec.update(data) + dec.finalize()

def aes_ecb_encrypt(key16: bytes, data: bytes) -> bytes:
    enc = Cipher(algorithms.AES(key16), modes.ECB(), default_backend()).encryptor()
    return enc.update(data) + enc.finalize()

def folder_master_key(folder_key_b64: str) -> bytes:
    raw = b64url_decode(folder_key_b64)
    if len(raw) != 16:
        raise ValueError(f"folder key must be 16 bytes, got {len(raw)}")
    return raw

def decrypt_node_key(enc_key_b64: str, master16: bytes) -> bytes:
    enc = b64url_decode(enc_key_b64)
    if len(enc) not in (16, 32):
        raise ValueError(f"node enc key len {len(enc)}")
    if len(enc) == 16:
        return aes_ecb_decrypt(master16, enc)
    return aes_ecb_decrypt(master16, enc[:16]) + aes_ecb_decrypt(master16, enc[16:])

def fold_file_nodekey(node_key_32: bytes) -> tuple[bytes, bytes, bytes]:
    a = bytes_to_a32(node_key_32)
    if len(a) != 8:
        raise ValueError("file node key must fold from 8 a32 words")
    key = [a[0] ^ a[4], a[1] ^ a[5], a[2] ^ a[6], a[3] ^ a[7]]
    return a32_to_bytes(key), a32_to_bytes(a[4:6]), a32_to_bytes(a[6:8])

def mega_chunk_boundaries(size: int):
    p = 0
    i = 1
    while p < size:
        if i <= 8:
            n = 131072 * i
        else:
            n = 1048576
        n = min(n, size - p)
        yield p, n
        p += n
        i += 1

def chunk_mac(aes_key_16: bytes, nonce_8: bytes, chunk_bytes: bytes) -> list[int]:
    iv = nonce_8 + nonce_8
    enc = Cipher(algorithms.AES(aes_key_16), modes.CBC(iv), default_backend()).encryptor()
    pad = (-len(chunk_bytes)) % 16
    block = chunk_bytes + b"\x00" * pad
    ct = enc.update(block) + enc.finalize()
    last = ct[-16:]
    return bytes_to_a32(last)

def combine_file_mac(chunk_macs: list[list[int]], aes_key_16: bytes) -> list[int]:
    mac = [0, 0, 0, 0]
    for cm in chunk_macs:
        mac = [mac[0] ^ cm[0], mac[1] ^ cm[1], mac[2] ^ cm[2], mac[3] ^ cm[3]]
    mac_b = aes_ecb_encrypt(aes_key_16, a32_to_bytes(mac))
    return bytes_to_a32(mac_b)

def file_mac_matches(computed: list[int], expected_mac_seed_8: bytes) -> bool:
    exp = bytes_to_a32(expected_mac_seed_8)
    folded = [computed[0] ^ computed[1], computed[2] ^ computed[3]]
    return folded == exp
