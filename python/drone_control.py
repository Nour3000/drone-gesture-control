"""
drone_control.py — Relais UART -> BLE entre la STM32N6570-DK et le drone DRN2100.
pip install bleak pyserial
"""

import asyncio
import time
import serial
from bleak import BleakClient

# ==========================
# CONFIG
# ==========================
ADDRESS = "XX:XX:XX:XX:XX:XX"   # adresse BLE du drone (bluetoothctl scan on)
JOYSTICK_HANDLE = 36            # handle GATT confirmé

HZ = 20
PERIOD = 1.0 / HZ

SERIAL_PORT = "/dev/ttyACM0"
SERIAL_BAUD = 115200

HOVER_THROTTLE = 128

# payloads d'init
CALIBRATION = bytes([0, 0, 0, 0, 0, 0, 0x02])
ARMING      = bytes([0, 0, 0, 0, 0, 0, 0x04])

# ==========================
# LECTURE SÉRIE
# ==========================
def open_serial(port=SERIAL_PORT, baudrate=SERIAL_BAUD):
    return serial.Serial(port=port, baudrate=baudrate, timeout=0)

def read_from_stm32(ser):
    try:
        if ser.in_waiting > 0:
            line = ser.readline().decode("utf-8").strip()
            return line if line else None
    except Exception as e:
        print(f"[serial] erreur : {e}")
    return None

# ==========================
# PAYLOADS
# ==========================
def make_payload(yaw, throttle, roll, pitch):
    """trame 7 octets : [0, yaw, throttle, roll, pitch, 0, 0x04]"""
    throttle = max(0, min(255, throttle))
    return bytes([0, yaw, throttle, roll, pitch, 0, 0x04])

def translate_to_payload(gesture):
    """traduit la chaîne reçue de la STM32 en commande BLE"""
    mapping = {
        "stop":     make_payload(0, HOVER_THROTTLE, 0, 0),
        "waiting":  make_payload(0, HOVER_THROTTLE, 0, 0),
        "forward":  make_payload(0, HOVER_THROTTLE, 0, 170),
        "backward": make_payload(0, HOVER_THROTTLE, 0, 85),
        "left":     make_payload(85, HOVER_THROTTLE, 0, 0),
        "right":    make_payload(170, HOVER_THROTTLE, 0, 0),
        "up":       make_payload(0, 170, 0, 0),
        "down":     make_payload(0, 85, 0, 0),
    }
    # si geste inconnu ou None -> hover par sécurité
    return mapping.get(gesture, make_payload(0, HOVER_THROTTLE, 0, 0))

async def send_frames(client, payload, duration_s):
    """envoie le même payload à 20 Hz pendant duration_s (pour calib/armement)"""
    end = time.perf_counter() + duration_s
    next_t = time.perf_counter()
    while time.perf_counter() < end:
        await client.write_gatt_char(JOYSTICK_HANDLE, payload, response=False)
        next_t += PERIOD
        await asyncio.sleep(max(0, next_t - time.perf_counter()))

# ==========================
# MAIN
# ==========================
async def main():
    print(f"Connexion au drone ({ADDRESS})...")
    async with BleakClient(ADDRESS) as client:
        print("Connecté")

        print("Phase CALIBRATION (1s)")
        await send_frames(client, CALIBRATION, 1.0)

        print("Phase ARMEMENT (1s)")
        await send_frames(client, ARMING, 1.0)

        ser = open_serial()
        next_t = time.perf_counter()

        # par défaut on hover
        current_payload = translate_to_payload("stop")

        print("En attente des gestes STM32...")
        try:
            while True:
                gesture = read_from_stm32(ser)
                if gesture:
                    print(f"STM32: {gesture}")
                    current_payload = translate_to_payload(gesture)

                # envoi systématique à 20 Hz (watchdog du drone)
                await client.write_gatt_char(JOYSTICK_HANDLE, current_payload, response=False)

                next_t += PERIOD
                await asyncio.sleep(max(0, next_t - time.perf_counter()))

        except asyncio.CancelledError:
            print("\nArrêt — coupure moteurs")
            emergency = bytes([0, 0, 0, 0, 0, 0, 0x04])
            await client.write_gatt_char(JOYSTICK_HANDLE, emergency, response=False)
        finally:
            if ser and ser.is_open:
                ser.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgramme quitté.")
