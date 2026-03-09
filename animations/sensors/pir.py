# sensors/pir.py
# ─────────────────────────────────────────────────────────────────────────────
# PIR (passive infrared) motion sensor — single digital output pin.
#
# Fires one event per rising edge (LOW → HIGH transition) so a sustained
# presence only triggers once per approach, not every polling cycle.
#
# Wiring (HC-SR501 or similar):
#   VCC → Pin 2  (5V)   — PIR requires 5V, not 3.3V
#   GND → Pin 9  (GND)
#   OUT → Pin 7  (GPIO4)
# ─────────────────────────────────────────────────────────────────────────────

import time
import RPi.GPIO as GPIO
from typing import Callable
from animations.sensors.base import BaseSensor
import config as cfg


class PIRSensor(BaseSensor):
    def __init__(self, on_event: Callable[[str], None]):
        super().__init__("PIR", on_event)
        self.pin = cfg.PIR_PIN

    def _setup(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.IN)
        print(f"[PIR] GPIO{self.pin} ready")

    def _cleanup(self):
        GPIO.cleanup(self.pin)
        print(f"[PIR] GPIO{self.pin} cleaned up")

    def _loop(self):
        print("[PIR] Listening for motion...")
        was_high = False
        while self._running:
            current = GPIO.input(self.pin) == GPIO.HIGH
            if current and not was_high:
                self._emit("pir_motion")
            was_high = current
            time.sleep(0.05)
