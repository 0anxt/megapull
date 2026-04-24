import asyncio, httpx, itertools, random

async def test():
    API = "https://g.api.mega.co.nz/cs"
    _seq = itertools.count(random.randint(0, 0xFFFFFFFF))
    async with httpx.AsyncClient() as client:
        # Test file link a=g directly
        r = await client.post(API, params={"id": next(_seq)}, json=[{"a": "g", "g": 1, "ssl": 2, "p": "GF9mCC5A"}], timeout=10)
        print(f"a=g response: {r.json()}")

asyncio.run(test())