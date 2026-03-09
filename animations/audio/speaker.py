# audio/speaker.py
# ─────────────────────────────────────────────────────────────────────────────
# Speaker output — plays sounds and TTS responses.
#
# Currently a STUB. Uncomment and install dependencies when ready:
#   pip install pygame  (for sound files)
#   pip install pyttsx3 (for TTS)
#   OR use espeak directly via subprocess
#
# To activate:
#   1. Connect a speaker (USB audio, I2S DAC, or 3.5mm if your Pi has it)
#   2. pip install pygame
#   3. Set STUB_MODE = False below
#   4. Drop .wav/.mp3 files into audio/sounds/
# ─────────────────────────────────────────────────────────────────────────────

import time
import threading
import subprocess
from pathlib import Path
from typing import Optional

STUB_MODE   = True   # Set False when speaker hardware is connected
SOUNDS_DIR  = Path(__file__).parent / "sounds"

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


class Speaker:
    """
    Plays audio files and text-to-speech.
    All playback is non-blocking — runs in a daemon thread.
    """

    # Map sound names to filenames in audio/sounds/
    SOUND_MAP = {
        "happy":     "happy.wav",
        "sad":       "sad.wav",
        "angry":     "angry.wav",
        "laugh":     "laugh.wav",
        "surprised": "surprised.wav",
        "startup":   "startup.wav",
    }

    def __init__(self):
        self._lock    = threading.Lock()
        self._running = False

        if STUB_MODE or not PYGAME_AVAILABLE:
            print("[Speaker] STUB MODE — no audio output active")
            print("[Speaker] Install pygame and set STUB_MODE=False to enable")
            return

        pygame.mixer.init()
        SOUNDS_DIR.mkdir(exist_ok=True)
        print(f"[Speaker] Initialized — sounds dir: {SOUNDS_DIR}")

    def play_sound(self, name: str):
        """Play a named sound file non-blocking."""
        if STUB_MODE or not PYGAME_AVAILABLE:
            print(f"[Speaker] STUB play_sound({name})")
            return

        filename = self.SOUND_MAP.get(name)
        if not filename:
            print(f"[Speaker] Unknown sound '{name}'")
            return

        path = SOUNDS_DIR / filename
        if not path.exists():
            print(f"[Speaker] Sound file not found: {path}")
            return

        threading.Thread(
            target=self._play_file, args=(str(path),),
            daemon=True, name=f"Sound-{name}"
        ).start()

    def _play_file(self, path: str):
        with self._lock:
            try:
                sound = pygame.mixer.Sound(path)
                sound.play()
                # Wait for it to finish
                while pygame.mixer.get_busy():
                    time.sleep(0.05)
            except Exception as e:
                print(f"[Speaker] Playback error: {e}")

    def say(self, text: str):
        """
        Speak text using espeak (no extra deps, works on Pi out of the box).
        Non-blocking.
        """
        if STUB_MODE:
            print(f"[Speaker] STUB say: '{text}'")
            return

        threading.Thread(
            target=self._espeak, args=(text,),
            daemon=True, name="TTS"
        ).start()

    def _espeak(self, text: str):
        try:
            subprocess.run(
                ["espeak", "-s", "150", "-p", "60", text],
                check=True, capture_output=True
            )
        except FileNotFoundError:
            print("[Speaker] espeak not found — install with: sudo apt install espeak")
        except Exception as e:
            print(f"[Speaker] TTS error: {e}")

    def stop(self):
        if not STUB_MODE and PYGAME_AVAILABLE:
            pygame.mixer.stop()
        print("[Speaker] Stopped")
