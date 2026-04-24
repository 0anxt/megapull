import asyncio, httpx, itertools, random, base64

async def test():
    API = "https://g.api.mega.co.nz/cs"
    _seq = itertools.count(random.randint(0, 0xFFFFFFFF))

    # Decode the folder key to see if we need to send it differently
    key_b64 = "s20-5UCQdXaq7RQOvcazuQ"
    key_raw = base64.urlsafe_b64decode(key_b64 + "=" * (-len(key_b64) % 4))
    print(f"Folder key raw: {key_raw.hex()}")
    print(f"Folder key len: {len(key_raw)}")

    async with httpx.AsyncClient() as client:
        params = {"id": next(_seq), "n": "t71iEBJQ"}

        # Try: a=f with folder key in 'k' param
        payload1 = [{"a": "f", "n": "t71iEBJQ", "k": key_b64, "c": 1}]
        r1 = await client.post(API, params=params, json=payload1, timeout=10)
        print("a=f with k= in payload:", r1.text[:200])

        # Try: include the key as raw base64 in the request body
        payload2 = [{"a": "f", "n": "t71iEBJQ", "key": key_raw.hex(), "c": 1}]
        r2 = await client.post(API, params=params, json=payload2, timeout=10)
        print("a=f with key=raw:", r2.text[:200])

        # Try: get folder session with 'n' param AND include key in payload  
        payload3 = [{"a": "f", "c": 1, "r": 1, "ca": 1, "n": "t71iEBJQ", "k": key_b64}]
        r3 = await client.post(API, params=params, json=payload3, timeout=10)
        print("a=f with n+t71iEBJQ + k= in payload:", r3.text[:200])

        # NEW THEORY: maybe the folder handle format needs to match exactly
        # What if we need to use the full URL-encoded folder link as context?
        params2 = {"id": next(_seq), "n": "t71iEBJQ", "n2": "folder/t71iEBJQ"}
        payload4 = [{"a": "f", "c": 1}]
        r4 = await client.post(API, params=params2, json=payload4, timeout=10)
        print("a=f with n2 param:", r4.text[:200])

asyncio.run(test())