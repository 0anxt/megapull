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
        b += b'\x00' * (4 - len(b) % 4)
    return list(struct.unpack(f'>{len(b)//4}I', b))

def a32_to_bytes(a: list[int]) -> bytes:
    return struct.pack(f'>{len(a)}I', *a)

def derive_file_key_iv(file_key_b64: str) -> tuple[bytes, bytes, bytes]:
    """Returns (aes_key_16, ctr_nonce_8, mac_seed_8) from a public file key."""
    raw = b64url_decode(file_key_b64)
    a = bytes_to_a32(raw)
    if len(a) != 8:
        raise ValueError(f"bad file key length: expected 8 a32 words, got {len(a)}")
    key = [a[0]^a[4], a[1]^a[5], a[2]^a[6], a[3]^a[7]]
    return a32_to_bytes(key), a32_to_bytes(a[4:6]), a32_to_bytes(a[6:8])

def folder_master_key(folder_key_b64: str) -> bytes:
    """Returns 16-byte master key from a folder key (16 raw bytes, base64url)."""
    raw = b64url_decode(folder_key_b64)
    if len(raw) != 16:
        raise ValueError(f"folder key must be 16 bytes, got {len(raw)}")
    return raw

def aes_ecb_decrypt(key16: bytes, data: bytes) -> bytes:
    dec = Cipher(algorithms.AES(key16), modes.ECB(), default_backend()).decryptor()
    return dec.update(data) + dec.finalize()

def decrypt_node_key(enc_key_b64: str | bytes, master16: bytes) -> bytes:
    """Decrypt a node key (16 or 32 bytes encrypted) using folder master key."""
    if isinstance(enc_key_b64, bytes):
        enc = enc_key_b64
    else:
        enc = b64url_decode(enc_key_b64)
    if len(enc) not in (16, 32):
        raise ValueError(f"node enc key len {len(enc)}, expected 16 or 32")
    if len(enc) == 16:
        return aes_ecb_decrypt(master16, enc)
    return aes_ecb_decrypt(master16, enc[:16]) + aes_ecb_decrypt(master16, enc[16:])

def fold_file_nodekey(node_key_32: bytes) -> tuple[bytes, bytes, bytes]:
    """Fold 32B MEGA file node-key -> (aes_key_16, ctr_nonce_8, mac_seed_8)."""
    a = bytes_to_a32(node_key_32)
    if len(a) != 8:
        raise ValueError("file node key must fold from 8 a32 words")
    key = [a[0]^a[4], a[1]^a[5], a[2]^a[6], a[3]^a[7]]
    return a32_to_bytes(key), a32_to_bytes(a[4:6]), a32_to_bytes(a[6:8])

def decrypt_attributes(enc_b64: str, key16: bytes) -> dict:
    data = b64url_decode(enc_b64)
    dec = Cipher(algorithms.AES(key16), modes.CBC(b'\x00'*16), default_backend()).decryptor()
    out = dec.update(data) + dec.finalize()
    if not out.startswith(b'MEGA'):
        raise ValueError(f"attr decrypt failed: missing MEGA prefix, got {out[:4]!r}")
    return json.loads(out[4:].rstrip(b'\x00').decode())

def aes_ctr_decryptor(key16: bytes, nonce8: bytes, start_block: int = 0):
    """AES-128-CTR with 16-byte IV = nonce8 || counter_u64_be."""
    iv = nonce8 + start_block.to_bytes(8, 'big')
    return Cipher(algorithms.AES(key16), modes.CTR(iv), default_backend()).decryptor()