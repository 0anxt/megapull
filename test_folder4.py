import asyncio, httpx, itertools, random

async def test():
    API = "https://g.api.mega.co.nz/cs"
    _seq = itertools.count(random.randint(0, 0xFFFFFFFF))

    async with httpx.AsyncClient() as client:
        # First enumerate the folder
        params = {"id": next(_seq), "n": "t71iEBJQ", "n2": "folder/t71iEBJQ"}
        r = await client.post(API, params=params, json=[{"a": "f", "c": 1}], timeout=10)
        print("Folder enum response:", r.text[:500])

asyncio.run(test())