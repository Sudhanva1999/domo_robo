# sensors/base.py
# ─────────────────────────────────────────────────────────────────────────────
# Abstract base class for all sensors.
#
# Every sensor:
#   - Runs in its own daemon thread
#   - Fires named string events via a callback: on_event(event_name: str)
#   - Never touches the display or controller directly
#   - Cleans up its own hardware resources on stop()
#
# To add a new sensor:
#   1. Create sensors/mysensor.py
#   2. Subclass BaseSensor
#   3. Implement _setup() and _loop()
#   4. Call self._emit("event_name") when something happens
#   5. Register it in main.py
# ─────────────────────────────────────────────────────────────────────────────

import threading
from abc import ABC, abstractmethod
from typing import Callable


class BaseSensor(ABC):
    """
    Base class for all sensors.

    Subclasses implement _setup() and _loop().
    _loop() runs in a daemon thread and should check self._running.
    Call self._emit(event) to fire an event to the controller.
    """

    def __init__(self, name: str, on_event: Callable[[str], None]):
        self.name      = name
        self._on_event = on_event
        self._running  = False
        self._thread   = None

    def _emit(self, event: str):
        """Fire a named event to whoever is listening (the controller)."""
        print(f"[{self.name}] Event → {event}")
        self._on_event(event)

    @abstractmethod
    def _setup(self):
        """Initialize hardware. Called once before the loop starts."""
        pass

    @abstractmethod
    def _loop(self):
        """
        Main sensor loop. Runs in a thread.
        Must check self._running and exit cleanly when it's False.
        """
        pass

    def _cleanup(self):
        """Optional hardware cleanup on stop. Override if needed."""
        pass

    def start(self):
        """Initialize hardware and start the sensor thread."""
        print(f"[{self.name}] Starting...")
        self._setup()
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop, name=self.name, daemon=True)
        self._thread.start()
        print(f"[{self.name}] Running on thread '{self.name}'")

    def stop(self):
        """Stop the sensor loop and clean up hardware."""
        print(f"[{self.name}] Stopping...")
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self._cleanup()
        print(f"[{self.name}] Stopped")
