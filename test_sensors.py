# test_sensors.py
# ─────────────────────────────────────────────────────────────────────────────
# Standalone sensor test — no display required.
# Starts all sensors and prints every event they fire to stdout.
#
# Usage:
#   python test_sensors.py           — test all sensors
#   python test_sensors.py touch     — test touch only
#   python test_sensors.py pir       — test pir only
#
# Press Ctrl+C to stop.
# ─────────────────────────────────────────────────────────────────────────────

import sys
import time
import threading

from animations.sensors.touch import TouchSensor
from animations.sensors.pir   import PIRSensor
import config as cfg

# ── Event counts ──────────────────────────────────────────────────────────────

counts = {}
counts_lock = threading.Lock()

def on_event(event: str):
    now = time.strftime("%H:%M:%S")
    with counts_lock:
        counts[event] = counts.get(event, 0) + 1
        total = counts[event]
    print(f"[{now}]  {event:<22}  (#{total})")

# ── Sensor selection ──────────────────────────────────────────────────────────

arg = sys.argv[1].lower() if len(sys.argv) > 1 else "all"

sensors = []

if arg in ("all", "touch"):
    sensors.append(TouchSensor(on_event=on_event))

if arg in ("all", "pir"):
    sensors.append(PIRSensor(on_event=on_event))

if not sensors:
    print(f"Unknown sensor '{arg}'. Choose: all | touch | pir")
    sys.exit(1)

# ── Run ───────────────────────────────────────────────────────────────────────

print("─" * 50)
print("  Sensor test — waiting for events")
print(f"  Touch pin : GPIO{cfg.TOUCH_PIN}  (Pin 11)")
print(f"  PIR pin   : GPIO{cfg.PIR_PIN}   (Pin 7)")
print("─" * 50)
print()

for s in sensors:
    s.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    print("\nStopping sensors...")
    for s in sensors:
        s.stop()
    print("\nEvent summary:")
    if counts:
        for event, n in sorted(counts.items()):
            print(f"  {event:<22} {n}x")
    else:
        print("  (no events received)")
