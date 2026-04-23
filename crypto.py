from __future__ import annotations
import base64, struct, json
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


def b64url_decode(s: str) -> bytes:
    s = s + '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode())


def b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip('=')


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
        raise ValueError("bad file key length")
    key = [a[0]^a[4], a[1]^a[5], a[2]^a[6], a[3]^a[7]]
    iv = a[4:6]
    mac = a[6:8]
    return a32_to_bytes(key), a32_to_bytes(iv), a32_to_bytes(mac)


def aes_ctr_decryptor(key16: bytes, nonce8: bytes, start_block: int = 0):
    """AES-128-CTR with 16-byte IV = nonce8 || counter_u64_be."""
    iv = nonce8 + start_block.to_bytes(8, 'big')
    return Cipher(algorithms.AES(key16), modes.CTR(iv), default_backend()).decryptor()


def decrypt_attributes(enc_b64: str, key16: bytes) -> dict:
    data = b64url_decode(enc_b64)
    dec = Cipher(algorithms.AES(key16), modes.CBC(b'\x00'*16), default_backend()).decryptor()
    out = dec.update(data) + dec.finalize()
    if not out.startswith(b'MEGA'):
        raise ValueError("attr decrypt failed")
    return json.loads(out[4:].rstrip(b'\x00').decode())