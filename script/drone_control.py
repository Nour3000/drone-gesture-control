"""
drone_control.py
================
Script relais UART -> BLE assurant l'interface entre la carte STM32N6570-DK
et le drone ST DRN2100.

Fonctionnement :
  1. Lecture non-bloquante des chaînes textuelles émises par la STM32 (ex: "forward").
  2. Traduction du geste en coordonnées de vol (Yaw, Throttle, Roll, Pitch).
  3. Envoi asynchrone et continu des payloads GATT BLE à une fréquence de 20 Hz.

Prérequis :
  pip install bleak pyserial
"""

import asyncio
import time
import serial
from bleak import BleakClient

# ==============================================================================
# CONFIGURATION MATÉRIELLE
# ==============================================================================
ADDRESS = "C0:28:6A:35:2F:33"  
JOYSTICK_HANDLE = 36           

HZ = 20
PERIOD = 1.0 / HZ

SERIAL_PORT = "/dev/ttyACM0"   
SERIAL_BAUD = 115200

# Paramètres de vol
HOVER_THROTTLE = 128           # Puissance par défaut pour le vol stationnaire

# Payloads d'initialisation du contrôleur de vol
CALIBRATION = bytes([0, 0, 0, 0, 0, 0, 0x02])
ARMING      = bytes([0, 0, 0, 0, 0, 0, 0x04])

# ==============================================================================
# GESTION DU PORT SÉRIE (STM32)
# ==============================================================================
def open_serial(port=SERIAL_PORT, baudrate=SERIAL_BAUD):
    """Ouvre le port série en mode non-bloquant (timeout=0)."""
    return serial.Serial(port=port, baudrate=baudrate, timeout=0)

def read_from_stm32(ser):
    """Lit une commande textuelle disponible sur le buffer série."""
    try:
        if ser.in_waiting > 0:
            line = ser.readline().decode("utf-8").strip()
            return line if line else None
    except Exception as e:
        print(f"[Serial] Erreur de lecture : {e}")
    return None

# ==============================================================================
# ENCAPSULATION DU PROTOCOLE DE VOL
# ==============================================================================
def make_payload(yaw: int, throttle: int, roll: int, pitch: int) -> bytes:
    """Formate la trame de 7 octets requise par le contrôleur de vol ST."""
    throttle = max(0, min(255, throttle))
    # Structure attendue : [0, yaw, throttle, roll, pitch, 0, command_type]
    return bytes([0, yaw, throttle, roll, pitch, 0, 0x04])

def translate_to_payload(gesture: str) -> bytes:
    """Associe un mot-clé reçu de la STM32 à sa trame de commande BLE."""
    mapping = {
        "stop":     make_payload(0, HOVER_THROTTLE, 0, 0),
        "waiting":  make_payload(0, HOVER_THROTTLE, 0, 0),
        "takeoff":  make_payload(0, 170, 0, 0),
        "up":       make_payload(0, 170, 0, 0),
        "down":     make_payload(0, 85, 0, 0),
        "forward":  make_payload(0, HOVER_THROTTLE, 0, 170),
        "backward": make_payload(0, HOVER_THROTTLE, 0, 85),
        "left":     make_payload(85, HOVER_THROTTLE, 0, 0),
        "right":    make_payload(170, HOVER_THROTTLE, 0, 0),
    }
    # Sécurité active : si aucun geste ou chaîne inconnue -> Maintien stationnaire
    return mapping.get(gesture, make_payload(0, HOVER_THROTTLE, 0, 0))

async def send_frames(client, payload, duration_s):
    """Envoie un même payload de configuration à 20 Hz pendant un temps donné."""
    end = time.perf_counter() + duration_s
    next_t = time.perf_counter()
    while time.perf_counter() < end:
        await client.write_gatt_char(JOYSTICK_HANDLE, payload, response=False)
        next_t += PERIOD
        await asyncio.sleep(max(0, next_t - time.perf_counter()))

# ==============================================================================
# BOUCLE PRINCIPALE ASYNCHRONE
# ==============================================================================
async def main():
    print(f"[BLE] Connexion au drone à l'adresse {ADDRESS}...")
    async with BleakClient(ADDRESS) as client:
        print("[BLE] Liaison établie avec succès ✓")

        print("[Init] Phase 1/2 — CALIBRATION du drone (1s)...")
        await send_frames(client, CALIBRATION, 1.0)

        print("[Init] Phase 2/2 — ARMEMENT des moteurs (1s)...")
        await send_frames(client, ARMING, 1.0)

        print("[Loop] Liaison temps réel active. Écoute des paquets STM32...")
        ser = open_serial()
        next_t = time.perf_counter()
        
        # Initialisation de la trame courante par défaut (sécurité au démarrage)
        current_payload = translate_to_payload("stop")

        try:
            while True:
                gesture = read_from_stm32(ser)
                if gesture:
                    print(f"[Geste Reçu] -> {gesture}")
                    current_payload = translate_to_payload(gesture)

                # Envoi systématique à 20 Hz pour rafraîchir le Watchdog du drone
                await client.write_gatt_char(JOYSTICK_HANDLE, current_payload, response=False)
                
                next_t += PERIOD
                await asyncio.sleep(max(0, next_t - time.perf_counter()))

        except asyncio.CancelledError:
            print("\n[Stop] Interruption demandée. Arrêt d'urgence des moteurs...")
            # Envoi d'un payload de sécurité (toutes consignes à zéro)
            emergency_stop = bytes([0, 0, 0, 0, 0, 0, 0x04])
            await client.write_gatt_char(JOYSTICK_HANDLE, emergency_stop, response=False)
        finally:
            if ser and ser.is_open:
                ser.close()
                print("[Serial] Port série fermé.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgramme quitté par l'utilisateur.")