"""
throttle_test.py — Test de la liaison BLE : rampe de throttle 0 -> 255 -> 0
pip install bleak
"""

import asyncio
from bleak import BleakClient

ADDRESS = "XX:XX:XX:XX:XX:XX"   # adresse BLE du drone
JOYSTICK_HANDLE = 36

CALIBRATION = bytes([0, 0, 0, 0, 0, 0, 0x02])
ARMING      = bytes([0, 0, 0, 0, 0, 0, 0x04])

THROTTLE_STEP = 5

async def main():
    print(f"Connexion au drone ({ADDRESS})...")
    async with BleakClient(ADDRESS) as client:
        print("Connecté")

        # calibration 1s
        print("Calibration...")
        for _ in range(20):
            await client.write_gatt_char(JOYSTICK_HANDLE, CALIBRATION, response=False)
            await asyncio.sleep(0.05)

        # armement 1s
        print("Armement...")
        for _ in range(20):
            await client.write_gatt_char(JOYSTICK_HANDLE, ARMING, response=False)
            await asyncio.sleep(0.05)

        # rampe de throttle
        print("Throttle 0 -> 255 -> 0")
        throttle = 0
        direction = 1
        try:
            while True:
                throttle = max(0, min(255, throttle))
                # [0, yaw, throttle, roll, pitch, 0, commande]
                payload = bytes([0, 0x80, throttle, 0x80, 0x80, 0, 0x04])
                await client.write_gatt_char(JOYSTICK_HANDLE, payload, response=False)

                throttle += direction * THROTTLE_STEP
                if throttle >= 255:
                    direction = -1
                elif throttle <= 0:
                    direction = 1

                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            print("Arrêt")

        # coupe les gaz
        clear = bytes([0, 0, 0, 0, 0, 0, 0x04])
        await client.write_gatt_char(JOYSTICK_HANDLE, clear, response=False)
        print("Fin du test")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrompu.")
