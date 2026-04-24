import asyncio, httpx, itertools, random

async def test():
    API = "https://g.api.mega.co.nz/cs"
    _seq = itertools.count(random.randint(0, 0xFFFFFFFF))
    
    async with httpx.AsyncClient() as client:
        # Try dz8CEBZR as the actual root folder
        params = {"id": next(_seq), "n": "dz8CEBZR", "n2": "folder/dz8CEBZR"}
        r = await client.post(API, params=params, json=[{"a": "f", "c": 1}], timeout=10)
        print(f"dz8CEBZR as root: {str(r.json())[:300]}")

asyncio.run(test())