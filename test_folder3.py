import asyncio, httpx, itertools, random

async def test():
    API = "https://g.api.mega.co.nz/cs"
    _seq = itertools.count(random.randint(0, 0xFFFFFFFF))

    async with httpx.AsyncClient() as client:
        base_params = {"id": next(_seq)}

        # Test 1: n2 only
        params1 = {"id": next(_seq), "n2": "t71iEBJQ"}
        r1 = await client.post(API, params=params1, json=[{"a": "f", "c": 1}], timeout=10)
        print("n2=t71iEBJQ only:", r1.text[:150])

        # Test 2: n2 with folder prefix
        params2 = {"id": next(_seq), "n2": "folder/t71iEBJQ"}
        r2 = await client.post(API, params=params2, json=[{"a": "f", "c": 1}], timeout=10)
        print("n2=folder/t71iEBJQ:", r2.text[:150])

        # Test 3: n param combined with n2
        params3 = {"id": next(_seq), "n": "t71iEBJQ", "n2": "folder/t71iEBJQ"}
        r3 = await client.post(API, params=params3, json=[{"a": "f", "c": 1}], timeout=10)
        print("n + n2:", r3.text[:150])

        # Test 4: What is n2 exactly? Maybe it's the folder key in a specific format?
        # Let's try with the key as n2
        params4 = {"id": next(_seq), "n2": "s20-5UCQdXaq7RQOvcazuQ"}
        r4 = await client.post(API, params=params4, json=[{"a": "f", "c": 1}], timeout=10)
        print("n2=folder_key:", r4.text[:150])

asyncio.run(test())