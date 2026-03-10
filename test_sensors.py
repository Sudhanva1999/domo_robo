# test_sensors.py
# ─────────────────────────────────────────────────────────────────────────────
# Standalone sensor test — no display required.
#
# Usage:
#   python test_sensors.py                  test all sensors (event mode)
#   python test_sensors.py touch            test touch only
#   python test_sensors.py pir              test PIR only
#   python test_sensors.py raw              raw GPIO levels for all pins
#   python test_sensors.py raw touch        raw GPIO level for touch pin only
#   python test_sensors.py raw pir          raw GPIO level for PIR pin only
#
# Must be run as root on the Pi:  sudo python test_sensors.py
# Press Ctrl+C to stop.
# ─────────────────────────────────────────────────────────────────────────────

import sys
import time
import threading

# ── Check root ────────────────────────────────────────────────────────────────

import os
if os.geteuid() != 0:
    print("WARNING: not running as root — GPIO access may fail.")
    print("         Try: sudo python test_sensors.py\n")

# ── Import GPIO ───────────────────────────────────────────────────────────────

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("ERROR: RPi.GPIO not found. Install with: pip install RPi.GPIO")
    sys.exit(1)

import config as cfg

# ── Parse args ────────────────────────────────────────────────────────────────
# Accepted forms:
#   test_sensors.py
#   test_sensors.py touch | pir | all
#   test_sensors.py raw
#   test_sensors.py raw touch | pir | all

args  = [a.lower() for a in sys.argv[1:]]
raw   = "raw" in args
which = next((a for a in args if a in ("touch", "pir", "all")), "all")

# ── Pin map ───────────────────────────────────────────────────────────────────

PINS = {
    "touch": ("Touch", cfg.TOUCH_PIN),
    "pir":   ("PIR",   cfg.PIR_PIN),
}

selected = {k: v for k, v in PINS.items() if which == "all" or which == k}

# ─────────────────────────────────────────────────────────────────────────────
# RAW MODE — poll GPIO directly, print every level change
# ─────────────────────────────────────────────────────────────────────────────

def run_raw():
    GPIO.setmode(GPIO.BCM)
    for name, pin in selected.values():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        print(f"  {name:<6} GPIO{pin}  set up as INPUT with pull-down")

    print()
    print("Polling every 50 ms — printing every read.")
    print("(Hold Ctrl+C to stop)\n")

    try:
        while True:
            ts = time.strftime('%H:%M:%S.') + f'{int(time.time()*1000)%1000:03d}'
            parts = []
            for name, pin in selected.values():
                level = GPIO.input(pin)
                state = "HIGH" if level else "LOW "
                parts.append(f"{name:<6} GPIO{pin}: {state}")
            print(f"[{ts}]  {'   '.join(parts)}")
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
        print("\nGPIO cleaned up.")

# ─────────────────────────────────────────────────────────────────────────────
# EVENT MODE — run full sensor classes, print classified events
# ─────────────────────────────────────────────────────────────────────────────

def run_events():
    from animations.sensors.touch import TouchSensor
    from animations.sensors.pir   import PIRSensor

    counts      = {}
    counts_lock = threading.Lock()

    def on_event(event: str):
        now = time.strftime("%H:%M:%S")
        with counts_lock:
            counts[event] = counts.get(event, 0) + 1
            n = counts[event]
        print(f"[{now}]  {event:<22}  (#{n})")

    sensors = []
    try:
        if "touch" in selected:
            sensors.append(TouchSensor(on_event=on_event))
        if "pir" in selected:
            sensors.append(PIRSensor(on_event=on_event))
    except Exception as e:
        print(f"ERROR creating sensor: {e}")
        sys.exit(1)

    for s in sensors:
        try:
            s.start()
            print(f"  {s.name} sensor started.")
        except Exception as e:
            print(f"ERROR starting {s.name}: {e}")

    print()
    print("Waiting for events... (Ctrl+C to stop)\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nStopping sensors...")
        for s in sensors:
            try:
                s.stop()
            except Exception:
                pass

        print("\nEvent summary:")
        if counts:
            for event, n in sorted(counts.items()):
                print(f"  {event:<22}  {n}x")
        else:
            print("  (no events received)")

# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

print("─" * 52)
print("  domo sensor test")
print(f"  mode    : {'raw GPIO' if raw else 'event (classified)'}")
print(f"  sensors : {', '.join(n for n, _ in selected.values())}")
print(f"  touch   : GPIO{cfg.TOUCH_PIN}  (Pin 11)")
print(f"  pir     : GPIO{cfg.PIR_PIN}   (Pin 7)")
print("─" * 52)
print()

if raw:
    run_raw()
else:
    run_events()
