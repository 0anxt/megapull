import asyncio, httpx, itertools, random

async def test():
    API = "https://g.api.mega.co.nz/cs"
    _seq = itertools.count(random.randint(0, 0xFFFFFFFF))

    folder_id = "t71iEBJQ"
    folder_key_b64 = "s20-5UCQdXaq7RQOvcazuQ"

    async with httpx.AsyncClient(http2=True) as client:
        params = {"id": next(_seq), "n": folder_id, "n2": f"folder/{folder_id}"}
        payload = [{"a": "f", "r": 1, "c": 1}]

        r = await client.post(API, params=params, json=payload, timeout=30)
        data = r.json()

        if isinstance(data, list) and len(data) > 0:
            nodes = data[0].get("f", [])
            print(f"Total nodes: {len(nodes)}")

            from crypto import folder_master_key, b64url_decode
            master = folder_master_key(folder_key_b64)

            for i, node in enumerate(nodes[:5]):
                t = node.get("t")
                h = node.get("h")
                k = node.get("k", "")
                print(f"\nNode {i}: t={t}, h={h}")
                print(f"  k={k!r}")
                print(f"  k len (str)={len(k)}")
                if k:
                    if ":" in k:
                        parts = k.split(":")
                        print(f"  : split -> {parts}")
                        for j, p in enumerate(parts):
                            try:
                                raw = b64url_decode(p)
                                print(f"    part[{j}] raw len: {len(raw)}")
                            except Exception as e:
                                print(f"    part[{j}] ERROR: {e}")

asyncio.run(test())