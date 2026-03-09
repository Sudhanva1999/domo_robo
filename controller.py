# controller.py
# ─────────────────────────────────────────────────────────────────────────────
# Central controller — the only place that connects sensors to the display.
#
# Design:
#   - Sensors fire string events:  "touch_tap", "voice_loud", etc.
#   - Controller looks up each event in config.EVENT_MAP
#   - Dispatches "play:<anim>" or "mood:<mood>" to RoboEyes
#   - Optionally triggers audio via Speaker
#   - All sensors and audio modules register themselves here
#
# To add a new sensor:
#   1. Build it in sensors/mysensor.py (extend BaseSensor)
#   2. Add its events to config.EVENT_MAP
#   3. Register it in controller.register_sensor()
#   That's it — no other file needs to change.
#
# Priority system:
#   Events have an optional priority (default=5, higher=more important).
#   If an event comes in while a high-priority animation is running,
#   low-priority events are dropped. Adjust PRIORITY_MAP as needed.
# ─────────────────────────────────────────────────────────────────────────────

import time
import threading
from typing import List

from animations.display.eyes import RoboEyes
from animations.audio.speaker import Speaker
from animations.sensors.base import BaseSensor
import config as cfg


# ── Priority map ──────────────────────────────────────────────────────────────
# Higher number = higher priority. Events below current threshold are dropped.

PRIORITY_MAP = {
    "touch_tap":        5,
    "touch_double_tap": 6,
    "touch_rub":        6,
    "touch_hold":       4,
    "voice_loud":       5,
    "voice_quiet":      3,
    "voice_laugh":      7,
    "keyword_hello":    8,
    "keyword_stop":     9,
}

DEFAULT_PRIORITY  = 5
COOLDOWN_SECS     = 0.8   # global minimum gap between any two dispatched events


class Controller:
    """
    Central brain. Owns RoboEyes and Speaker.
    Sensors and audio modules register with it and fire events into handle_event().
    """

    def __init__(self):
        self.eyes     = RoboEyes()
        self.speaker  = Speaker()
        self._sensors : List[BaseSensor] = []
        self._lock    = threading.Lock()

        self._last_event_time     = 0.0
        self._last_event_name     = None
        self._current_priority    = 0

        print("[Controller] Initialized")

    # ── Sensor registration ───────────────────────────────────────────────────

    def register_sensor(self, sensor: BaseSensor):
        """Register a sensor. Its events will be routed through handle_event."""
        self._sensors.append(sensor)
        print(f"[Controller] Registered sensor → {sensor.name}")

    # ── Event handling ────────────────────────────────────────────────────────

    def handle_event(self, event: str):
        """
        Called by any sensor when something happens.
        Thread-safe — sensors run in their own threads.
        """
        now      = time.time()
        priority = PRIORITY_MAP.get(event, DEFAULT_PRIORITY)

        with self._lock:
            # Global cooldown check
            elapsed = now - self._last_event_time
            if elapsed < COOLDOWN_SECS:
                print(f"[Controller] Dropped '{event}' — global cooldown "
                      f"({elapsed:.2f}s < {COOLDOWN_SECS}s)")
                return

            # Priority check — don't interrupt high-priority animations
            if priority < self._current_priority:
                print(f"[Controller] Dropped '{event}' — "
                      f"priority {priority} < current {self._current_priority}")
                return

            action = cfg.EVENT_MAP.get(event)
            if not action:
                print(f"[Controller] No mapping for event '{event}' — ignoring")
                return

            self._last_event_time  = now
            self._last_event_name  = event
            self._current_priority = priority

        print(f"[Controller] Event '{event}' → action '{action}'")
        self._dispatch(action, event)

        # Reset priority after a short window so future events aren't blocked forever
        threading.Timer(2.0, self._reset_priority, args=[priority]).start()

    def _reset_priority(self, released_priority: int):
        with self._lock:
            if self._current_priority == released_priority:
                self._current_priority = 0

    # ── Action dispatch ───────────────────────────────────────────────────────

    def _dispatch(self, action: str, source_event: str):
        """Parse and execute a "play:<x>" or "mood:<x>" action string."""
        if action.startswith("play:"):
            anim = action[5:]
            self.eyes.play(anim)
            self._maybe_play_sound(anim)

        elif action.startswith("mood:"):
            mood = action[5:]
            self.eyes.set_mood(mood)

        else:
            print(f"[Controller] Unknown action format '{action}'")

    def _maybe_play_sound(self, animation: str):
        """Play a matching sound if one exists for this animation."""
        sound_triggers = {"happy", "sad", "angry", "laugh", "surprised"}
        if animation in sound_triggers:
            self.speaker.play_sound(animation)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        """Start the display, all registered sensors, and audio."""
        print("[Controller] Starting all systems...")
        self.eyes.start()

        for sensor in self._sensors:
            sensor.start()

        print(f"[Controller] Running — "
              f"{len(self._sensors)} sensor(s) active")

    def stop(self):
        """Gracefully stop everything."""
        print("[Controller] Shutting down...")

        for sensor in self._sensors:
            sensor.stop()

        self.speaker.stop()
        self.eyes.stop()
        print("[Controller] All systems stopped")

    # ── Direct control (for CLI / testing) ───────────────────────────────────

    def play(self, animation: str):
        """Directly queue an animation, bypassing the event map."""
        self.eyes.play(animation)

    def set_mood(self, mood: str):
        """Directly set a mood, bypassing the event map."""
        self.eyes.set_mood(mood)
