import asyncio, httpx, itertools, random

async def test():
    API = "https://g.api.mega.co.nz/cs"
    _seq = itertools.count(random.randint(0, 0xFFFFFFFF))

    async with httpx.AsyncClient() as client:
        params = {"id": next(_seq), "n": "t71iEBJQ"}

        # a=g with n= inside folder session
        payload = [{"a": "g", "g": 1, "ssl": 2, "n": "43k01DqK"}]
        r = await client.post(API, params=params, json=payload, timeout=10)
        print("folder session a=g with n=:", r.text[:200])

        # a=g with p= in folder session
        payload2 = [{"a": "g", "g": 1, "ssl": 2, "p": "43k01DqK"}]
        r2 = await client.post(API, params=params, json=payload2, timeout=10)
        print("folder session a=g with p=:", r2.text[:200])

asyncio.run(test())