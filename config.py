# config.py
# ─────────────────────────────────────────────────────────────────────────────
# Central configuration — change pins, timings, and behaviour here.
# Nothing else in the codebase should contain magic numbers.
# ─────────────────────────────────────────────────────────────────────────────

# ── Display SPI pins (match your wiring) ─────────────────────────────────────
DISPLAY_DC_PIN  = 24    # GPIO24 — Pin 18
DISPLAY_RST_PIN = 25    # GPIO25 — Pin 22
DISPLAY_CS_PIN  = 0     # CE0    — Pin 24
DISPLAY_BAUDRATE = 64_000_000

# ── Sensor GPIO pins ──────────────────────────────────────────────────────────
TOUCH_PIN = 17          # GPIO17 — Pin 11

# ── Touch gesture timing (seconds) ───────────────────────────────────────────
TOUCH_DEBOUNCE       = 0.04   # ignore transitions shorter than this
TOUCH_TAP_MAX        = 0.25   # HIGH duration shorter than this = tap
TOUCH_HOLD_MIN       = 0.60   # HIGH duration longer than this = hold
TOUCH_RUB_WINDOW     = 0.80   # look for transitions within this window
TOUCH_RUB_MIN_FLICKS = 3      # min transitions in window to count as rub
TOUCH_DOUBLE_TAP_GAP = 0.35   # max gap between two taps for double-tap
TOUCH_COOLDOWN       = 1.5    # min seconds between any two gesture triggers

# ── Eye layout ────────────────────────────────────────────────────────────────
EYE_W       = 82
EYE_H       = 92
EYE_R       = 20
EYE_GAP     = 126
EYE_Y       = 120   # centre of 240 px landscape canvas height
FRAME_DT    = 0.016     # ~60 fps

# ── Eye colors ────────────────────────────────────────────────────────────────
COL_DEFAULT  = (0,   180, 255)
COL_HAPPY    = (0,   215, 175)
COL_ANGRY    = (255,  45,  15)
COL_SAD      = (25,   95, 195)
COL_TIRED    = (55,  115, 170)
COL_SURPRISE = (0,   215, 255)
COL_TEAR     = (90,  170, 255)
COL_BG       = (8,    8,   18)

# ── Idle behaviour ────────────────────────────────────────────────────────────
IDLE_BLINK_MIN  = 2.0
IDLE_BLINK_MAX  = 5.5
IDLE_GLANCE_MIN = 4.0
IDLE_GLANCE_MAX = 9.0

# ── Audio (for future mic/speaker) ───────────────────────────────────────────
AUDIO_SAMPLE_RATE    = 16000
AUDIO_CHANNELS       = 1
AUDIO_CHUNK_SIZE     = 512
AUDIO_INPUT_DEVICE   = None    # None = system default
AUDIO_OUTPUT_DEVICE  = None    # None = system default
AUDIO_VAD_THRESHOLD  = 0.02    # voice activity detection energy threshold
AUDIO_SILENCE_TIMEOUT = 1.5    # seconds of silence before speech ends

# ── Controller event → animation mapping ─────────────────────────────────────
# Edit this to change what each sensor event triggers.
# Keys are event names fired by sensors.
# Values are either:
#   "play:<animation>"  — one-shot animation
#   "mood:<mood>"       — persistent mood change
EVENT_MAP = {
    # Touch gestures
    "touch_tap":        "play:surprised",
    "touch_double_tap": "play:happy",
    "touch_rub":        "play:laugh",
    "touch_hold":       "play:happy",

    # Audio events (wired up when mic is added)
    "voice_loud":       "play:angry",
    "voice_laugh":      "play:laugh",
    "voice_quiet":      "play:tired",
    "keyword_hello":    "play:happy",
    "keyword_stop":     "mood:tired",
}
