# sensors/touch.py
# ─────────────────────────────────────────────────────────────────────────────
# Capacitive touch sensor (TTP223 or similar — single digital IO pin).
#
# Detects four gesture types by analyzing the timing of HIGH/LOW transitions:
#
#   touch_tap         Short clean press  (< TAP_MAX duration)
#   touch_double_tap  Two taps with gap  (< DOUBLE_TAP_GAP apart)
#   touch_hold        Finger held down   (> HOLD_MIN duration)
#   touch_rub         Rapid flickering   (>= RUB_MIN_FLICKS in RUB_WINDOW)
#
# Fires events via the callback passed to BaseSensor.
# All timing constants live in config.py.
# ─────────────────────────────────────────────────────────────────────────────

import time
import RPi.GPIO as GPIO
from typing import Callable
from animations.sensors.base import BaseSensor
import config as cfg


class TouchSensor(BaseSensor):
    def __init__(self, on_event: Callable[[str], None]):
        super().__init__("Touch", on_event)
        self.pin = cfg.TOUCH_PIN

    # ── BaseSensor interface ──────────────────────────────────────────────────

    def _setup(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        print(f"[Touch] GPIO{self.pin} ready")

    def _cleanup(self):
        GPIO.cleanup(self.pin)
        print(f"[Touch] GPIO{self.pin} cleaned up")

    def _loop(self):
        print("[Touch] Listening — tap / double-tap / hold / rub")

        # ── State ─────────────────────────────────────────────────────────────
        raw               = False   # last raw GPIO reading
        debounced         = False   # last stable (debounced) state
        last_change_time  = time.time()

        touch_start       = None    # when current touch began
        last_release_time = None    # when last touch ended (for double-tap)

        # Rub detection: sliding window of recent transition timestamps
        transition_times  = []

        gesture_count = {"tap": 0, "double_tap": 0, "hold": 0, "rub": 0}

        while self._running:
            now     = time.time()
            current = GPIO.input(self.pin) == GPIO.HIGH

            # ── Debounce ──────────────────────────────────────────────────────
            if current != raw:
                raw              = current
                last_change_time = now

            stable = (now - last_change_time) >= cfg.TOUCH_DEBOUNCE

            if not stable:
                time.sleep(0.005)
                continue

            # ── Rising edge (touch start) ─────────────────────────────────────
            if current and not debounced:
                debounced   = current
                touch_start = now
                transition_times.append(now)
                print(f"[Touch] ↓ Press detected")

            # ── Falling edge (touch end) ──────────────────────────────────────
            elif not current and debounced:
                debounced = current

                if touch_start is None:
                    time.sleep(0.005)
                    continue

                duration = now - touch_start
                transition_times.append(now)

                # Prune transitions outside the rub window
                transition_times = [
                    t for t in transition_times
                    if now - t <= cfg.TOUCH_RUB_WINDOW
                ]

                print(f"[Touch] ↑ Release — duration {duration:.3f}s  "
                      f"transitions in window: {len(transition_times)}")

                # ── Classify gesture ──────────────────────────────────────────

                # Rub: enough rapid transitions in a short window
                if len(transition_times) >= cfg.TOUCH_RUB_MIN_FLICKS * 2:
                    gesture_count["rub"] += 1
                    print(f"[Touch] ✓ Rub #{gesture_count['rub']}")
                    self._emit("touch_rub")
                    transition_times.clear()
                    last_release_time = None

                # Hold: long single press
                elif duration >= cfg.TOUCH_HOLD_MIN:
                    gesture_count["hold"] += 1
                    print(f"[Touch] ✓ Hold #{gesture_count['hold']} "
                          f"({duration:.2f}s)")
                    self._emit("touch_hold")
                    last_release_time = None

                # Short press — could be tap or first of a double-tap
                elif duration <= cfg.TOUCH_TAP_MAX:
                    if (last_release_time is not None and
                            now - last_release_time <= cfg.TOUCH_DOUBLE_TAP_GAP):
                        # Second tap close enough → double tap
                        gesture_count["double_tap"] += 1
                        print(f"[Touch] ✓ Double-tap #{gesture_count['double_tap']}")
                        self._emit("touch_double_tap")
                        last_release_time = None
                    else:
                        # First tap — wait briefly to see if a second follows
                        last_release_time = now

                touch_start = None

            # ── Pending single tap timeout ────────────────────────────────────
            # If enough time has passed since a tap with no follow-up, emit it.
            if (last_release_time is not None and
                    now - last_release_time > cfg.TOUCH_DOUBLE_TAP_GAP):
                gesture_count["tap"] += 1
                print(f"[Touch] ✓ Tap #{gesture_count['tap']}")
                self._emit("touch_tap")
                last_release_time = None

            time.sleep(0.005)
