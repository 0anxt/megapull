import asyncio, httpx, itertools, random

async def test():
    API = "https://g.api.mega.co.nz/cs"
    _seq = itertools.count(random.randint(0, 0xFFFFFFFF))
    
    # Same client for session persistence
    async with httpx.AsyncClient() as client:
        # Establish folder session on parent
        params = {"id": next(_seq), "n": "t71iEBJQ", "n2": "folder/t71iEBJQ"}
        r1 = await client.post(API, params=params, json=[{"a": "f", "c": 1}], timeout=10)
        print(f"a=f session: {r1.json()}")
        
        # Now try a=g on a subfolder handle using SAME client
        for sub_h in ["dz8CEBZR", "43k01DqK"]:
            r2 = await client.post(API, params={"id": next(_seq), "n": sub_h},
                json=[{"a": "g", "g": 1, "ssl": 2, "n": sub_h}], timeout=10)
            print(f"a=g n={sub_h}: {r2.json()}")
            
            r3 = await client.post(API, params={"id": next(_seq), "n": sub_h},
                json=[{"a": "g", "g": 1, "ssl": 2, "p": sub_h}], timeout=10)
            print(f"a=g p={sub_h}: {r3.json()}")

asyncio.run(test())