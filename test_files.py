import asyncio, httpx, itertools, random
from crypto import folder_master_key, decrypt_node_key, fold_file_nodekey, decrypt_attributes

async def test():
    API = "https://g.api.mega.co.nz/cs"
    _seq = itertools.count(random.randint(0, 0xFFFFFFFF))
    folder_id = "t71iEBJQ"
    folder_key_b64 = "s20-5UCQdXaq7RQOvcazuQ"

    async with httpx.AsyncClient(http2=True) as client:
        params = {"id": next(_seq), "n": folder_id, "n2": f"folder/{folder_id}"}
        r = await client.post(API, params=params, json=[{"a": "f", "r": 1, "c": 1}], timeout=30)
        nodes = r.json()[0].get("f", [])

        master = folder_master_key(folder_key_b64)
        print(f"Total nodes: {len(nodes)}")
        print(f"File nodes (t=0):")
        
        for i, n in enumerate(nodes):
            if n.get("t") == 0:
                h = n.get("h")
                k = n.get("k", "")
                a = n.get("a", "")
                print(f"  handle={h}, k={k!r}")
                try:
                    key_part = k.split(":")[1]
                    node_key_32 = decrypt_node_key(key_part, master)
                    key16, nonce8, mac_seed = fold_file_nodekey(node_key_32)
                    print(f"    -> decrypted OK, key16={key16.hex()[:16]}...")
                    attr = decrypt_attributes(a, key16)
                    name = attr.get("n", "?")
                    print(f"    -> name: {name}")
                except Exception as e:
                    print(f"    -> ERROR: {e}")

asyncio.run(test())