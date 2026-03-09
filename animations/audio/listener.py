# audio/listener.py
# ─────────────────────────────────────────────────────────────────────────────
# Microphone listener — detects voice activity and audio events.
#
# Currently a STUB. Uncomment and install dependencies when ready:
#   pip install pyaudio numpy
#
# Events fired:
#   voice_loud      — sustained loud audio detected
#   voice_quiet     — audio drops back to silence after being loud
#   voice_laugh     — laughter-like rhythm detected (rapid amplitude bursts)
#   keyword_hello   — (future) wake word detected
#   keyword_stop    — (future) stop keyword detected
#
# To activate:
#   1. Connect a USB mic or I2S mic to the Pi
#   2. pip install pyaudio numpy
#   3. Remove the STUB_MODE block in _setup() below
#   4. Register MicListener in main.py (already stubbed there)
# ─────────────────────────────────────────────────────────────────────────────

import time
import threading
from typing import Callable
from animations.sensors.base import BaseSensor
import config as cfg

STUB_MODE = True   # Set False when mic hardware is connected

try:
    import pyaudio
    import numpy as np
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False


class MicListener(BaseSensor):
    """
    Listens to microphone input and fires events based on audio characteristics.
    Runs in its own daemon thread via BaseSensor.
    """

    def __init__(self, on_event: Callable[[str], None]):
        super().__init__("Mic", on_event)
        self._stream     = None
        self._pa         = None
        self._loud_since = None   # timestamp when loud audio started

    # ── BaseSensor interface ──────────────────────────────────────────────────

    def _setup(self):
        if STUB_MODE or not PYAUDIO_AVAILABLE:
            print("[Mic] STUB MODE — no microphone hardware active")
            print("[Mic] Install pyaudio + numpy and set STUB_MODE=False to enable")
            return

        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format            = pyaudio.paInt16,
            channels          = cfg.AUDIO_CHANNELS,
            rate              = cfg.AUDIO_SAMPLE_RATE,
            input             = True,
            input_device_index= cfg.AUDIO_INPUT_DEVICE,
            frames_per_buffer = cfg.AUDIO_CHUNK_SIZE,
        )
        print(f"[Mic] Stream opened — {cfg.AUDIO_SAMPLE_RATE}Hz "
              f"chunk={cfg.AUDIO_CHUNK_SIZE}")

    def _cleanup(self):
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        if self._pa:
            self._pa.terminate()
        print("[Mic] Stream closed")

    def _loop(self):
        if STUB_MODE or not PYAUDIO_AVAILABLE:
            # Stub loop — just idles until stopped
            print("[Mic] Stub loop running (no events will fire)")
            while self._running:
                time.sleep(0.5)
            return

        print("[Mic] Listening for audio events...")

        burst_times = []   # timestamps of recent amplitude bursts (laugh detection)

        while self._running:
            try:
                raw  = self._stream.read(cfg.AUDIO_CHUNK_SIZE,
                                         exception_on_overflow=False)
                data = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                rms  = float(np.sqrt(np.mean(data ** 2))) / 32768.0
                now  = time.time()

                # ── Loud detection ────────────────────────────────────────────
                if rms > cfg.AUDIO_VAD_THRESHOLD:
                    if self._loud_since is None:
                        self._loud_since = now
                        print(f"[Mic] Audio detected (rms={rms:.4f})")
                    elif now - self._loud_since > 0.6:
                        self._emit("voice_loud")
                        self._loud_since = now   # re-arm after emit

                    # Burst tracking for laugh detection
                    burst_times.append(now)
                    burst_times = [t for t in burst_times if now - t < 1.5]

                else:
                    if self._loud_since is not None:
                        print(f"[Mic] Silence resumed (rms={rms:.4f})")
                        self._emit("voice_quiet")
                        self._loud_since = None

                # ── Laugh detection (rapid bursts) ────────────────────────────
                if len(burst_times) >= 5:
                    gaps = [burst_times[i+1] - burst_times[i]
                            for i in range(len(burst_times)-1)]
                    avg_gap = sum(gaps) / len(gaps)
                    if 0.08 < avg_gap < 0.35:
                        print(f"[Mic] Laugh pattern detected (avg gap {avg_gap:.2f}s)")
                        self._emit("voice_laugh")
                        burst_times.clear()

            except Exception as e:
                print(f"[Mic] Stream error: {e}")
                time.sleep(0.1)
