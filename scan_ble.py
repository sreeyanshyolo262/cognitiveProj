"""List nearby BLE devices so you can confirm the car's module is visible."""
import asyncio
from bleak import BleakScanner

async def main():
    found = await BleakScanner.discover(timeout=8.0, return_adv=True)
    for addr, (dev, adv) in found.items():
        print(f"{dev.name or adv.local_name or '(no name)':25} {addr}  rssi={adv.rssi}")

asyncio.run(main())
