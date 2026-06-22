"""
throttle_test.py
================
Script de test unitaire pour valider la communication BLE GATT et la montée 
progressive des moteurs du drone ST DRN2100 de manière isolée.

Usage:
    python throttle_test.py
"""

import asyncio
from bleak import BleakClient

ADDRESS = "C0:28:6A:35:2F:33"  # Adresse MAC 
JOYSTICK_HANDLE = 36           # Handle caractéristique GATT

# Commandes de configuration brutes (1 octet d'action à la fin)
CALIBRATION = bytes([0, 0, 0, 0, 0, 0, 0x02])
ARMING      = bytes([0, 0, 0, 0, 0, 0, 0x04])

async def main():
    print(f"[Test] Connexion au drone à l'adresse : {ADDRESS}...")
    async with BleakClient(ADDRESS) as client:
        print("[Test] Connecté. Lancement de la phase de calibration (1s)...")
        for _ in range(20):  # 20 itérations à 50ms = 1 seconde
            await client.write_gatt_char(JOYSTICK_HANDLE, CALIBRATION, response=False)
            await asyncio.sleep(0.05)

        print("[Test] Phase d'armement des moteurs (1s)...")
        for _ in range(20):
            await client.write_gatt_char(JOYSTICK_HANDLE, ARMING, response=False)
            await asyncio.sleep(0.05)

        print("[Test] Envol progressif : Envoi d'une poussée légère (Throttle = 140)...")
        # Structure de test : [0, yaw, throttle (140), roll, pitch, 0, commande_vol (0x04)]
        payload_test = bytes([0, 0, 140, 0, 0, 0, 0x04])
        for _ in range(40):  # Test dynamique pendant 2 secondes
            await client.write_gatt_char(JOYSTICK_HANDLE, payload_test, response=False)
            await asyncio.sleep(0.05)

        print("[Test] Fin de la séquence — Arrêt de sécurité des moteurs")
        # Coupe les gaz immédiatement en laissant le drone armé ou au sol
        clear_payload = bytes([0, 0, 0, 0, 0, 0, 0x04])
        await client.write_gatt_char(JOYSTICK_HANDLE, clear_payload, response=False)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrompu par l'utilisateur.")