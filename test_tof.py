# test_tof.py
# ─────────────────────────────────────────────────────────────────────────────
# Standalone Time-of-Flight sensor test — no display or controller required.
#
# Wiring (VL53L0X / VL53L1X breakout):
#   VIN  → Pin 1  (3.3V)
#   GND  → Pin 9  (GND)
#   SDA  → Pin 3  (GPIO2 / I2C1 SDA)
#   SCL  → Pin 5  (GPIO3 / I2C1 SCL)
#   INT  → Pin 7  (GPIO4)   — optional, used in interrupt mode below
#   SHUT → Pin 29 (GPIO5)   — optional, driven HIGH here to enable sensor
#
# Pre-requisites:
#   sudo raspi-config → Interface Options → I2C → Enable
#   pip install adafruit-circuitpython-vl53l0x      (for VL53L0X)
#   pip install adafruit-circuitpython-vl53l1x      (for VL53L1X)
#
# Usage:
#   sudo python test_tof.py              continuous distance readings
#   sudo python test_tof.py scan         I2C bus scan only (no sensor needed)
# ─────────────────────────────────────────────────────────────────────────────

import sys
import time
import os

# ── Root check ────────────────────────────────────────────────────────────────

if os.geteuid() != 0:
    print("WARNING: not running as root — GPIO/I2C access may fail.")
    print("         Try: sudo python test_tof.py\n")

# ── GPIO/I2C imports ──────────────────────────────────────────────────────────

try:
    import board
    import busio
    import digitalio
except ImportError:
    print("ERROR: adafruit-blinka not found.")
    print("       pip install adafruit-blinka")
    sys.exit(1)

# ── I2C scan mode ─────────────────────────────────────────────────────────────
# Useful first step: confirms the sensor is visible on the bus before trying
# to talk to it.  VL53L0X default address is 0x29.

if len(sys.argv) > 1 and sys.argv[1].lower() == "scan":
    import smbus2
    bus = smbus2.SMBus(1)
    print("Scanning I2C bus 1 (SDA=GPIO2, SCL=GPIO3)...\n")
    found = []
    for addr in range(0x03, 0x78):
        try:
            bus.read_byte(addr)
            found.append(addr)
            print(f"  Found device at 0x{addr:02X}")
        except Exception:
            pass
    bus.close()
    if not found:
        print("  No devices found.")
        print("  Check wiring and that I2C is enabled (sudo raspi-config).")
    else:
        print(f"\n{len(found)} device(s) found.")
        if 0x29 in found:
            print("  0x29 → VL53L0X/VL53L1X default address ✓")
    sys.exit(0)

# ── SHUT pin — pull HIGH to enable sensor ─────────────────────────────────────

try:
    shut = digitalio.DigitalInOut(board.D5)   # GPIO5, Pin 29
    shut.direction = digitalio.Direction.OUTPUT
    shut.value = True
    time.sleep(0.05)                           # give sensor time to boot
    print("SHUT (GPIO5) → HIGH  — sensor enabled")
except Exception as e:
    print(f"NOTE: could not drive SHUT pin: {e}")
    print("      Continuing — sensor may already be up.\n")

# ── INT pin — set as input for interrupt detection ────────────────────────────

try:
    import RPi.GPIO as GPIO
    INT_PIN = 4                                # GPIO4, Pin 7
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(INT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    int_available = True
    print(f"INT  (GPIO{INT_PIN}) → INPUT  — interrupt monitoring active")
except Exception as e:
    int_available = False
    print(f"NOTE: could not set up INT pin: {e}")

print()

# ── Sensor init ───────────────────────────────────────────────────────────────

i2c = busio.I2C(board.SCL, board.SDA)

sensor = None
sensor_model = None

try:
    import adafruit_vl53l1x
    sensor = adafruit_vl53l1x.VL53L1X(i2c)
    sensor.distance_mode = 1          # 1 = short (up to ~1.3 m, faster)
                                      # 2 = long  (up to ~4 m, slower)
    sensor.timing_budget = 50         # ms per measurement (20–1000)
    sensor.start_ranging()
    sensor_model = "VL53L1X"
except (ImportError, Exception):
    pass

if sensor is None:
    try:
        import adafruit_vl53l0x
        sensor = adafruit_vl53l0x.VL53L0X(i2c)
        sensor.measurement_timing_budget = 50000   # 50 ms in microseconds
        sensor_model = "VL53L0X"
    except (ImportError, Exception) as e:
        print(f"ERROR: could not initialise ToF sensor: {e}")
        print()
        print("Install the library for your sensor:")
        print("  VL53L1X:  pip install adafruit-circuitpython-vl53l1x")
        print("  VL53L0X:  pip install adafruit-circuitpython-vl53l0x")
        sys.exit(1)

print(f"Sensor   : {sensor_model}  (I2C address 0x29)")
print(f"Interval : ~100 ms per print")
print()
print(f"{'TIME':>12}  {'DIST (mm)':>9}  {'DIST (cm)':>9}  {'INT':>4}  BAR")
print("─" * 72)

# ── Read loop ─────────────────────────────────────────────────────────────────

MAX_BAR_MM = 500   # distance that fills the bar completely

try:
    while True:
        ts = time.strftime("%H:%M:%S")

        try:
            if sensor_model == "VL53L1X":
                # VL53L1X uses data_ready flag
                while not sensor.data_ready:
                    time.sleep(0.005)
                dist_mm = sensor.distance
                sensor.clear_interrupt()
                if dist_mm is None:
                    raise ValueError("out of range")
                dist_mm = int(dist_mm * 10)   # returns cm, convert to mm
            else:
                dist_mm = sensor.range        # VL53L0X returns mm directly

            dist_cm  = dist_mm / 10
            bar_len  = min(30, int(dist_mm / MAX_BAR_MM * 30))
            bar      = "█" * bar_len + "░" * (30 - bar_len)
            int_flag = "LOW" if (int_available and not GPIO.input(INT_PIN)) else "---"

            print(f"{ts:>12}  {dist_mm:>9}  {dist_cm:>9.1f}  {int_flag:>4}  {bar}")

        except Exception as e:
            print(f"{ts:>12}  {'--':>9}  {'--':>9}  {'---':>4}  ({e})")

        time.sleep(0.1)

except KeyboardInterrupt:
    pass
finally:
    if sensor_model == "VL53L1X":
        try:
            sensor.stop_ranging()
        except Exception:
            pass
    if int_available:
        GPIO.cleanup()
    print("\nStopped.")
