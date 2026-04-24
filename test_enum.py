import asyncio, httpx, itertools, random, base64

async def test():
    API = "https://g.api.mega.co.nz/cs"
    _seq = itertools.count(random.randint(0, 0xFFFFFFFF))
    async with httpx.AsyncClient() as client:
        params = {"id": next(_seq), "n": "t71iEBJQ", "n2": "folder/t71iEBJQ"}
        r = await client.post(API, params=params, json=[{"a": "f", "c": 1}], timeout=10)
        data = r.json()
        nodes = data[0].get("f", [])
        print(f"Total nodes: {len(nodes)}")
        master_key = base64.urlsafe_b64decode("s20-5UCQdXaq7RQOvcazuQ" + "==")
        for n in nodes:
            t = n.get("t", 0)
            h = n.get("h", "?")
            s = n.get("s", "?")
            a = n.get("a", "")
            k = n.get("k", "")
            print(f"  handle={h} type={t} size={s} attr={a[:40]}..." if a else f"  handle={h} type={t} size={s}")
            if k:
                print(f"    encrypted_key={k}")

asyncio.run(test())