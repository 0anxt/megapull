import asyncio, httpx, itertools, random, base64

async def test():
    API = "https://g.api.mega.co.nz/cs"
    _seq = itertools.count(random.randint(0, 0xFFFFFFFF))
    async with httpx.AsyncClient() as client:
        # Step 1: Get folder contents of t71iEBJQ
        params = {"id": next(_seq), "n": "t71iEBJQ", "n2": "folder/t71iEBJQ"}
        r = await client.post(API, params=params, json=[{"a": "f", "c": 1}], timeout=10)
        data = r.json()
        nodes = data[0].get("f", [])
        print(f"Folder t71iEBJQ has {len(nodes)} items")
        
        # For each subfolder (type=1), try to enumerate it
        for n in nodes:
            t = n.get("t", 0)
            h = n.get("h", "?")
            k = n.get("k", "")
            if t == 1:  # subfolder
                print(f"\nSubfolder handle={h}")
                # The node key for this subfolder is encrypted with the parent master key
                # First decrypt the node key
                parent_master = base64.urlsafe_b64decode("s20-5UCQdXaq7RQOvcazuQ==")
                # node key format: "parent_handle:encrypted_key" 
                if ":" in k:
                    pk = k.split(":")[1]
                else:
                    pk = k
                enc = base64.urlsafe_b64decode(pk + "==")
                # AES-ECB decrypt
                from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
                from cryptography.hazmat.backends import default_backend
                dec = Cipher(algorithms.AES(parent_master), modes.ECB(), default_backend()).decryptor()
                node_key = dec.update(enc) + dec.finalize()
                print(f"  decrypted node key (hex): {node_key.hex()}")
                
                # Now try to enumerate this subfolder using its handle + node_key
                sub_params = {"id": next(_seq), "n": h, "n2": f"folder/{h}"}
                r2 = await client.post(API, params=sub_params, json=[{"a": "f", "c": 1}], timeout=10)
                data2 = r2.json()
                print(f"  API response: {str(data2)[:200]}")
                
                # Try a=g to get file download URL
                r3 = await client.post(API, params={"id": next(_seq), "n": h}, 
                    json=[{"a": "g", "g": 1, "ssl": 2, "n": h}], timeout=10)
                data3 = r3.json()
                print(f"  g API: {str(data3)[:200]}")

asyncio.run(test())