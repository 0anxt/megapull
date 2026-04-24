"""Debug the MEGA folder API call."""
import asyncio, httpx, itertools, random, struct, base64

API = "https://g.api.mega.co.nz/cs"
_seq = itertools.count(random.randint(0, 0xFFFFFFFF))

def b64url_decode(s):
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode())

def b64url_encode(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")

def bytes_to_a32(b):
    if len(b) % 4:
        b += b"\x00" * (4 - len(b) % 4)
    return list(struct.unpack(f">{len(b)//4}I", b))

async def test():
    folder_id = "t71iEBJQ"
    folder_key_b64 = "s20-5UCQdXaq7RQOvcazuQ"

    # Decode the folder key - check if it's actually 8 a32 words or something else
    key_raw = b64url_decode(folder_key_b64)
    print(f"Folder key raw bytes ({len(key_raw)}): {key_raw.hex()}")
    print(f"Folder key a32: {bytes_to_a32(key_raw)}")

    # Try different API formats
    async with httpx.AsyncClient() as client:
        params = {"id": next(_seq)}
        
        # Format 1: folder enumerate with n=folder_id
        payload1 = [{"a": "f", "n": folder_id, "r": 1, "c": 1}]
        r1 = await client.post(API, params=params, json=payload1, timeout=30)
        print(f"\nFormat 1 (n=folder_id): {r1.json()}")
        
        # Format 2: with no `c` param
        payload2 = [{"a": "f", "n": folder_id}]
        params2 = {"id": next(_seq)}
        r2 = await client.post(API, params=params2, json=payload2, timeout=30)
        print(f"Format 2 (no c): {r2.json()}")

        # Format 3: with just `a` and `n`
        payload3 = [{"a": "f", "n": folder_id, "c": 1}]
        params3 = {"id": next(_seq)}
        r3 = await client.post(API, params=params3, json=payload3, timeout=30)
        print(f"Format 3 (a,f,n,c): {r3.json()}")
        
        # Format 4: Check if folder handle format is different
        # Maybe the # folder format has a different n value
        # Try using the raw link parts differently
        print(f"\n--- Testing file link format for comparison ---")
        # A known working file link format
        payload4 = [{"a": "g", "g": 1, "ssl": 2, "p": "kgRdGTDb"}]
        params4 = {"id": next(_seq)}
        r4 = await client.post(API, params=params4, json=payload4, timeout=30)
        print(f"File g API (p=kgRdGTDb): {r4.json()[:2] if isinstance(r4.json(), list) else r4.json()}")

asyncio.run(test())