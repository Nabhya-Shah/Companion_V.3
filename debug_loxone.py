"""
Try controlling sub-controls (masterValue, AI1, AI2 dimmers).
"""
import asyncio
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("LOXONE_HOST", "192.168.0.200")
USER = os.getenv("LOXONE_USER", "")
PASSWORD = os.getenv("LOXONE_PASSWORD", "")

# Main controller UUID and sub-control UUIDs from structure file
MAIN_UUID = "10c3dd7e-035c-bb81-ffff01708c6be426"
MASTER_VALUE_UUID = "10c3dd7e-035c-bb81-ffff01708c6be426/masterValue"
AI1_UUID = "10c3dd7e-035c-bb81-ffff01708c6be426/AI1"
AI2_UUID = "10c3dd7e-035c-bb81-ffff01708c6be426/AI2"

async def try_subcontrols():
    base = f"http://{USER}:{PASSWORD}@{HOST}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Try masterValue dimmer with value 100 (full brightness)
        print("Trying masterValue at 100%...")
        url = f"{base}/jdev/sps/io/{MASTER_VALUE_UUID}/100"
        r = await client.get(url)
        data = r.json()
        print(f"masterValue 100: value={data.get('LL', {}).get('value')}, code={data.get('LL', {}).get('Code')}")
        
        await asyncio.sleep(1)
        
        # Try AI1 dimmer
        print("\nTrying AI1 dimmer at 100%...")
        url = f"{base}/jdev/sps/io/{AI1_UUID}/100"
        r = await client.get(url)
        data = r.json()
        print(f"AI1 100: value={data.get('LL', {}).get('value')}, code={data.get('LL', {}).get('Code')}")
        
        await asyncio.sleep(1)
        
        # Try AI2 dimmer
        print("\nTrying AI2 dimmer at 100%...")
        url = f"{base}/jdev/sps/io/{AI2_UUID}/100"
        r = await client.get(url)
        data = r.json()
        print(f"AI2 100: value={data.get('LL', {}).get('value')}, code={data.get('LL', {}).get('Code')}")
        
        print("\nCheck if lights turned on!")

if __name__ == "__main__":
    asyncio.run(try_subcontrols())
