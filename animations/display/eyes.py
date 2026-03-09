# display/eyes.py
# ─────────────────────────────────────────────────────────────────────────────
# RoboEyes display engine.
#
# Runs one background thread. Every animation is a generator that yields
# one Frame at a time. The engine calls next() each tick. Requests are
# queued and only picked up at natural animation boundaries — no mid-loop
# interruptions, no glitching.
#
# Public API (called by controller.py only):
#   eyes.start()
#   eyes.stop()
#   eyes.play(animation: str)
#   eyes.set_mood(mood: str)
# ─────────────────────────────────────────────────────────────────────────────

import board, busio, digitalio
from adafruit_rgb_display import ili9341
from PIL import Image, ImageDraw
import time, threading, random, math, queue
from dataclasses import dataclass, field
from typing import Optional

import config as cfg

# ── Display init ──────────────────────────────────────────────────────────────

def _init_display():
    cs  = digitalio.DigitalInOut(board.CE0)
    dc  = digitalio.DigitalInOut(board.D24)
    rst = digitalio.DigitalInOut(board.D25)
    spi = busio.SPI(clock=board.SCLK, MOSI=board.MOSI, MISO=board.MISO)
    return ili9341.ILI9341(spi, rotation=0, cs=cs, dc=dc, rst=rst,
                           baudrate=cfg.DISPLAY_BAUDRATE)

# ── Math helpers ──────────────────────────────────────────────────────────────

def lerp(a, b, t):             return a + (b - a) * t
def clamp(v, lo=0.0, hi=1.0):  return max(lo, min(hi, v))
def ease_out(t):               t=clamp(t); return 1-(1-t)**3
def ease_in(t):                t=clamp(t); return t*t
def ease_io(t):                t=clamp(t); return t*t*(3-2*t)
def col_lerp(a, b, t):         return tuple(int(lerp(x,y,t)) for x,y in zip(a,b))

def spring(t):
    t = clamp(t)
    return 1 - math.exp(-7*t) * math.cos(2*math.pi*t*1.15)

# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class EyeState:
    blink:       float = 0.0
    upper_lid:   float = 0.0
    lower_lid:   float = 0.0
    squash:      float = 1.0
    angle_inner: float = 0.0
    angle_outer: float = 0.0

    def lerp_to(self, o: "EyeState", t: float) -> "EyeState":
        return EyeState(
            lerp(self.blink,       o.blink,       t),
            lerp(self.upper_lid,   o.upper_lid,   t),
            lerp(self.lower_lid,   o.lower_lid,   t),
            lerp(self.squash,      o.squash,       t),
            lerp(self.angle_inner, o.angle_inner,  t),
            lerp(self.angle_outer, o.angle_outer,  t),
        )

@dataclass
class Tear:
    x: float; y: float; vy: float; size: float

@dataclass
class Frame:
    left:  EyeState
    right: EyeState
    color: tuple
    tears: list = field(default_factory=list)
    eye_y: int  = field(default_factory=lambda: cfg.EYE_Y)

NEUTRAL = EyeState()

# ── Mood state library ────────────────────────────────────────────────────────

MOOD_STATES = {
    "default":   (EyeState(),                                  EyeState(),                                  cfg.COL_DEFAULT),
    "happy":     (EyeState(lower_lid=0.45, squash=0.68),       EyeState(lower_lid=0.45, squash=0.68),       cfg.COL_HAPPY),
    "angry":     (EyeState(upper_lid=0.28, angle_inner=0.55),  EyeState(upper_lid=0.28, angle_inner=0.55),  cfg.COL_ANGRY),
    "sad":       (EyeState(upper_lid=0.18, angle_outer=0.50),  EyeState(upper_lid=0.18, angle_outer=0.50),  cfg.COL_SAD),
    "tired":     (EyeState(upper_lid=0.48, squash=0.82),       EyeState(upper_lid=0.48, squash=0.82),       cfg.COL_TIRED),
    "surprised": (EyeState(squash=1.30),                       EyeState(squash=1.30),                       cfg.COL_SURPRISE),
}

VALID_ANIMATIONS = {
    "blink", "look_left", "look_right", "look_up", "look_down",
    "happy", "angry", "sad", "surprised", "tired", "laugh", "confused",
    "anticipate",
}

# ── Drawing ───────────────────────────────────────────────────────────────────

def _draw_eye(draw, cx, cy, color, s: EyeState, flip: bool):
    # Eyes are drawn rotated 90°: EYE_H is the horizontal span, EYE_W the vertical.
    ew = max(4, int(cfg.EYE_H * s.squash))   # effective width  (horizontal)
    hh = cfg.EYE_W // 2                        # half-height      (vertical)
    x0 = cx - ew // 2;  y0 = cy - hh
    x1 = cx + ew // 2;  y1 = cy + hh

    draw.rounded_rectangle([x0, y0, x1, y1], radius=cfg.EYE_R, fill=color)

    eh = cfg.EYE_W                             # reference height for lid fractions
    top = clamp(s.blink*0.52 + s.upper_lid*0.50) * eh
    bot = clamp(s.blink*0.52 + s.lower_lid*0.40) * eh
    amp = int(eh * 0.55)

    ld = int((s.angle_outer if not flip else s.angle_inner) * amp)
    rd = int((s.angle_inner if not flip else s.angle_outer) * amp)

    base = y0 + int(top)
    if top > 0.5 or (ld + rd) > 0:
        draw.polygon([(x0-1,y0-1),(x1+1,y0-1),
                      (x1+1,base+rd),(x0-1,base+ld)], fill=cfg.COL_BG)
    if bot > 0.5:
        draw.rectangle([x0-1, y1-int(bot), x1+1, y1+1], fill=cfg.COL_BG)

    r = cfg.EYE_R
    for bx0,by0,bx1,by1 in [
        (x0-1,y0-1,x0+r,y0+r),(x1-r,y0-1,x1+1,y0+r),
        (x0-1,y1-r,x0+r,y1+1),(x1-r,y1-r,x1+1,y1+1)]:
        draw.rectangle([bx0,by0,bx1,by1], fill=cfg.COL_BG)

    draw.rounded_rectangle([x0,y0,x1,y1], radius=cfg.EYE_R, fill=color)

    if top > 0.5 or (ld + rd) > 0:
        draw.polygon([(x0-1,y0-1),(x1+1,y0-1),
                      (x1+1,base+rd),(x0-1,base+ld)], fill=cfg.COL_BG)
    if bot > 0.5:
        draw.rectangle([x0-1, y1-int(bot), x1+1, y1+1], fill=cfg.COL_BG)


def _draw_tears(draw, tears, cx, cy):
    for t in tears:
        r  = max(1, int(t.size))
        tx = int(cx + t.x)
        ty = int(t.y)
        draw.ellipse([tx-r, ty-r, tx+r, ty+r], fill=cfg.COL_TEAR)
        draw.polygon([(tx-r+1,ty-r+1),(tx+r-1,ty-r+1),(tx,ty-r*2)],
                     fill=cfg.COL_TEAR)

# ── Sub-animation building blocks ─────────────────────────────────────────────

def _blink_seq(l, r, c):
    cl = EyeState(1.0, l.upper_lid, l.lower_lid, l.squash, l.angle_inner, l.angle_outer)
    cr = EyeState(1.0, r.upper_lid, r.lower_lid, r.squash, r.angle_inner, r.angle_outer)
    for i in range(4):
        yield Frame(l.lerp_to(cl, ease_in(i/3)), r.lerp_to(cr, ease_in(i/3)), c)
    time.sleep(0.02)
    for i in range(6):
        yield Frame(cl.lerp_to(l, ease_out(i/5)), cr.lerp_to(r, ease_out(i/5)), c)


def _glance_seq(l, r, c, direction):
    sq_map = {
        "left":  (0.90, 1.05), "right": (1.05, 0.90),
        "up":    (0.86, 0.86), "down":  (1.10, 1.10),
    }
    sl, sr = sq_map.get(direction, (1.0, 1.0))
    dep = lambda s: EyeState(0, s.upper_lid, s.lower_lid, s.squash*0.88,
                              s.angle_inner, s.angle_outer)
    arr = lambda s, sq: EyeState(0, s.upper_lid, s.lower_lid, sq,
                                  s.angle_inner, s.angle_outer)
    dl, dr = dep(l), dep(r)
    al, ar = arr(l, sl), arr(r, sr)
    for i in range(3):
        yield Frame(l.lerp_to(dl, ease_in(i/2)), r.lerp_to(dr, ease_in(i/2)), c)
    for i in range(3):
        yield Frame(dl.lerp_to(al, ease_out(i/2)), dr.lerp_to(ar, ease_out(i/2)), c)
    for _ in range(random.randint(4, 10)):
        yield Frame(al, ar, c)
    for i in range(3):
        yield Frame(al.lerp_to(l, ease_out(i/2)), ar.lerp_to(r, ease_out(i/2)), c)


def _return_seq(l, r, c, mood, steps=7):
    ml, mr, mc = MOOD_STATES[mood]
    for i in range(steps):
        t = ease_out(i/(steps-1))
        yield Frame(l.lerp_to(ml,t), r.lerp_to(mr,t), col_lerp(c,mc,t))

# ── Animation generators ──────────────────────────────────────────────────────

def gen_startup():
    for i in range(20):
        t  = spring(i/19)
        sq = lerp(0.4, 1.12, clamp(t))
        b  = lerp(1.0, 0.0,  clamp(t))
        s  = EyeState(blink=b, squash=sq)
        yield Frame(s, s, cfg.COL_DEFAULT)
    settle = EyeState(squash=1.12)
    target = EyeState(squash=1.0)
    for i in range(8):
        s = settle.lerp_to(target, ease_out(i/7))
        yield Frame(s, s, cfg.COL_DEFAULT)
    for _ in range(10):
        yield Frame(target, target, cfg.COL_DEFAULT)
    yield from _blink_seq(target, target, cfg.COL_DEFAULT)
    for _ in range(15):
        yield Frame(NEUTRAL, NEUTRAL, cfg.COL_DEFAULT)


def gen_idle_settle(start_l, start_r, start_c, mood):
    ml, mr, mc = MOOD_STATES[mood]
    for i in range(7):
        t = ease_out(i/6)
        yield Frame(start_l.lerp_to(ml,t), start_r.lerp_to(mr,t),
                    col_lerp(start_c, mc, t))


def gen_idle_cycle(mood, timers):
    ml, mr, mc = MOOD_STATES[mood]
    timers.tick()
    if timers.blink_in <= 0:
        yield from _blink_seq(ml, mr, mc)
        timers.blink_in = random.uniform(cfg.IDLE_BLINK_MIN, cfg.IDLE_BLINK_MAX)
    elif timers.glance_in <= 0:
        yield from _glance_seq(ml, mr, mc,
                               random.choice(["left","right","up","down"]))
        timers.glance_in = random.uniform(cfg.IDLE_GLANCE_MIN, cfg.IDLE_GLANCE_MAX)
    else:
        yield Frame(ml, mr, mc)


def gen_blink(l, r, c, mood):
    yield from _blink_seq(l, r, c)
    yield from _return_seq(l, r, c, mood)

def gen_look(l, r, c, mood, direction):
    yield from _glance_seq(l, r, c, direction)
    yield from _return_seq(l, r, c, mood)

def gen_happy(l, r, c, mood):
    peak   = EyeState(lower_lid=0.60, squash=0.52)
    settle = EyeState(lower_lid=0.45, squash=0.68)
    tc     = cfg.COL_HAPPY
    for i in range(6):
        yield Frame(l.lerp_to(peak, ease_out(i/5)),
                    r.lerp_to(peak, ease_out(i/5)), col_lerp(c,tc,i/5))
    for i in range(4):
        yield Frame(peak.lerp_to(settle, ease_out(i/3)),
                    peak.lerp_to(settle, ease_out(i/3)), tc)
    for _ in range(2):
        up   = EyeState(lower_lid=0.55, squash=0.60)
        down = EyeState(lower_lid=0.38, squash=0.76)
        for i in range(3):
            yield Frame(settle.lerp_to(up,   ease_io(i/2)),
                        settle.lerp_to(up,   ease_io(i/2)), tc)
        for i in range(3):
            yield Frame(up.lerp_to(down,     ease_io(i/2)),
                        up.lerp_to(down,     ease_io(i/2)), tc)
        for i in range(3):
            yield Frame(down.lerp_to(settle, ease_io(i/2)),
                        down.lerp_to(settle, ease_io(i/2)), tc)
    for _ in range(20):
        yield Frame(settle, settle, tc)
    yield from _return_seq(settle, settle, tc, mood)

def gen_angry(l, r, c, mood):
    tl = EyeState(upper_lid=0.28, angle_inner=0.55)
    tc = cfg.COL_ANGRY
    for i in range(5):
        yield Frame(l.lerp_to(tl, ease_out(i/4)),
                    r.lerp_to(tl, ease_out(i/4)), col_lerp(c,tc,i/4))
    twitch = EyeState(upper_lid=0.38, angle_inner=0.65)
    for _ in range(3):
        for i in range(3):
            yield Frame(tl.lerp_to(twitch, ease_out(i/2)),
                        tl.lerp_to(twitch, ease_out(i/2)), tc)
        for i in range(3):
            yield Frame(twitch.lerp_to(tl, ease_out(i/2)),
                        twitch.lerp_to(tl, ease_out(i/2)), tc)
    for _ in range(25):
        yield Frame(tl, tl, tc)
    yield from _return_seq(tl, tl, tc, mood)

def gen_sad(l, r, c, mood):
    tl = EyeState(upper_lid=0.18, angle_outer=0.50)
    tc = cfg.COL_SAD
    for i in range(10):
        yield Frame(l.lerp_to(tl, ease_io(i/9)),
                    r.lerp_to(tl, ease_io(i/9)), col_lerp(c,tc,i/9))
    tears = [Tear(random.uniform(-6,6), cfg.EYE_Y+cfg.EYE_W//2,
                  random.uniform(5.0,8.0), random.uniform(4,7))
             for _ in range(2)]
    for fi in range(50):
        for t in tears:
            t.y   += t.vy
            t.size = max(0, t.size - 0.12)
        tears = [t for t in tears if t.size > 0.5 and t.y < 240]
        if len(tears) < 2 and fi < 35:
            tears.append(Tear(random.uniform(-6,6), cfg.EYE_Y+cfg.EYE_W//2,
                              random.uniform(5.0,8.0), random.uniform(4,7)))
        yield Frame(tl, tl, tc, tears=list(tears))
    yield from _blink_seq(tl, tl, tc)
    yield from _return_seq(tl, tl, tc, mood)

def gen_surprised(l, r, c, mood):
    wide   = EyeState(squash=1.35)
    settle = EyeState(squash=1.22)
    tc     = cfg.COL_SURPRISE
    for i in range(3):
        yield Frame(l.lerp_to(wide, ease_out(i/2)),
                    r.lerp_to(wide, ease_out(i/2)), col_lerp(c,tc,i/2))
    for i in range(6):
        yield Frame(wide.lerp_to(settle, ease_out(i/5)),
                    wide.lerp_to(settle, ease_out(i/5)), tc)
    for _ in range(18):
        yield Frame(settle, settle, tc)
    yield from _blink_seq(settle, settle, tc)
    yield from _return_seq(settle, settle, tc, mood)

def gen_tired(l, r, c, mood):
    tl = EyeState(upper_lid=0.48, squash=0.82)
    tc = cfg.COL_TIRED
    for i in range(15):
        yield Frame(l.lerp_to(tl, ease_io(i/14)),
                    r.lerp_to(tl, ease_io(i/14)), col_lerp(c,tc,i/14))
    half = EyeState(upper_lid=0.68, squash=0.80)
    for _ in range(2):
        for i in range(10):
            yield Frame(tl.lerp_to(half, ease_in(i/9)),
                        tl.lerp_to(half, ease_in(i/9)), tc)
        for _ in range(10):
            yield Frame(half, half, tc)
        for i in range(12):
            yield Frame(half.lerp_to(tl, ease_out(i/11)),
                        half.lerp_to(tl, ease_out(i/11)), tc)
        for _ in range(8):
            yield Frame(tl, tl, tc)
    yield from _return_seq(tl, tl, tc, mood)

def gen_laugh(l, r, c, mood):
    tc   = cfg.COL_HAPPY
    base = EyeState(lower_lid=0.30, squash=0.72)
    for i in range(5):
        yield Frame(l.lerp_to(base, ease_out(i/4)),
                    r.lerp_to(base, ease_out(i/4)), col_lerp(c,tc,i/4))
    for _ in range(7):
        up   = EyeState(lower_lid=0.38, squash=0.58)
        down = EyeState(lower_lid=0.22, squash=0.82)
        for i in range(3):
            yield Frame(base.lerp_to(up,   ease_io(i/2)),
                        base.lerp_to(up,   ease_io(i/2)), tc)
        for i in range(3):
            yield Frame(up.lerp_to(down,   ease_io(i/2)),
                        up.lerp_to(down,   ease_io(i/2)), tc)
        base = down
    yield from _return_seq(base, base, tc, mood)

def gen_confused(l, r, c, mood):
    lc = EyeState(angle_outer=0.45, squash=1.08)
    rc = EyeState(upper_lid=0.35, angle_inner=0.30, squash=0.90)
    tc = c
    for i in range(6):
        yield Frame(l.lerp_to(lc, ease_out(i/5)),
                    r.lerp_to(rc, ease_out(i/5)), tc)
    for _ in range(3):
        la = EyeState(angle_outer=0.50, squash=1.12)
        ra = EyeState(upper_lid=0.40, angle_inner=0.35, squash=0.88)
        lb = EyeState(angle_outer=0.38, squash=1.04)
        rb = EyeState(upper_lid=0.28, angle_inner=0.22, squash=0.94)
        for i in range(5):
            yield Frame(lc.lerp_to(la, ease_io(i/4)),
                        rc.lerp_to(ra, ease_io(i/4)), tc)
        for i in range(5):
            yield Frame(la.lerp_to(lb, ease_io(i/4)),
                        ra.lerp_to(rb, ease_io(i/4)), tc)
        lc, rc = lb, rb
    yield from _return_seq(lc, rc, tc, mood)

def gen_anticipate(l, r, c, mood):
    # Eyes slide to upper portion of canvas and narrow — anticipating a head pat.
    target_y = cfg.EYE_Y - 50          # shift upward (landscape canvas is 240px tall)
    tl = EyeState(upper_lid=0.18, squash=0.80)
    tc = c

    # Slide up and narrow
    for i in range(6):
        t  = ease_out(i/5)
        ey = int(lerp(cfg.EYE_Y, target_y, t))
        yield Frame(l.lerp_to(tl, t), r.lerp_to(tl, t), tc, eye_y=ey)

    # Eager anticipation: 3 small pulses while held at the top
    ea  = EyeState(upper_lid=0.22, squash=0.76)
    eb  = EyeState(upper_lid=0.14, squash=0.84)
    cur = tl
    for _ in range(3):
        for i in range(3):
            yield Frame(cur.lerp_to(ea, ease_io(i/2)),
                        cur.lerp_to(ea, ease_io(i/2)), tc, eye_y=target_y)
        for i in range(3):
            yield Frame(ea.lerp_to(eb, ease_io(i/2)),
                        ea.lerp_to(eb, ease_io(i/2)), tc, eye_y=target_y)
        cur = eb

    # Hold
    for _ in range(20):
        yield Frame(cur, cur, tc, eye_y=target_y)

    # Slide back down to mood state
    ml, mr, mc = MOOD_STATES[mood]
    for i in range(8):
        t  = ease_out(i/7)
        ey = int(lerp(target_y, cfg.EYE_Y, t))
        yield Frame(cur.lerp_to(ml, t), cur.lerp_to(mr, t),
                    col_lerp(tc, mc, t), eye_y=ey)


# ── Idle timers ───────────────────────────────────────────────────────────────

class _IdleTimers:
    def __init__(self):
        self.blink_in  = random.uniform(cfg.IDLE_BLINK_MIN,  cfg.IDLE_BLINK_MAX)
        self.glance_in = random.uniform(cfg.IDLE_GLANCE_MIN, cfg.IDLE_GLANCE_MAX)
        self.last      = time.time()

    def tick(self):
        now            = time.time()
        dt             = now - self.last
        self.last      = now
        self.blink_in  -= dt
        self.glance_in -= dt

# ── Animation dispatch ────────────────────────────────────────────────────────

def _build_generator(kind, l, r, c, mood):
    dispatch = {
        "blink":      lambda: gen_blink(l, r, c, mood),
        "look_left":  lambda: gen_look(l, r, c, mood, "left"),
        "look_right": lambda: gen_look(l, r, c, mood, "right"),
        "look_up":    lambda: gen_look(l, r, c, mood, "up"),
        "look_down":  lambda: gen_look(l, r, c, mood, "down"),
        "happy":      lambda: gen_happy(l, r, c, mood),
        "angry":      lambda: gen_angry(l, r, c, mood),
        "sad":        lambda: gen_sad(l, r, c, mood),
        "surprised":  lambda: gen_surprised(l, r, c, mood),
        "tired":      lambda: gen_tired(l, r, c, mood),
        "laugh":      lambda: gen_laugh(l, r, c, mood),
        "confused":   lambda: gen_confused(l, r, c, mood),
        "anticipate": lambda: gen_anticipate(l, r, c, mood),
    }
    fn = dispatch.get(kind)
    return fn() if fn else None

# ── RoboEyes engine ───────────────────────────────────────────────────────────

class RoboEyes:
    """
    Display engine. Accepts play() and set_mood() calls from the controller.
    Runs its own thread — never blocks the caller.
    """

    def __init__(self):
        self.disp = _init_display()
        self.W    = 320   # landscape canvas width  (display native height)
        self.H    = 240   # landscape canvas height (display native width)
        self.lx   = self.W // 2 - cfg.EYE_GAP // 2
        self.rx   = self.W // 2 + cfg.EYE_GAP // 2

        self._mood        = "default"
        self._cur_l       = EyeState()
        self._cur_r       = EyeState()
        self._cur_c       = cfg.COL_DEFAULT
        self._idle_timers = _IdleTimers()
        self._queue       = queue.Queue(maxsize=1)
        self._running     = False
        self._thread      = None
        print("[Eyes] Initialized")

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _push(self, frame: Frame):
        self._cur_l = frame.left
        self._cur_r = frame.right
        self._cur_c = frame.color
        img  = Image.new("RGB", (self.W, self.H), cfg.COL_BG)
        draw = ImageDraw.Draw(img)
        _draw_eye(draw, self.lx, frame.eye_y, frame.color, frame.left,  flip=False)
        _draw_eye(draw, self.rx, frame.eye_y, frame.color, frame.right, flip=True)
        if frame.tears:
            _draw_tears(draw, frame.tears, self.lx, frame.eye_y)
            _draw_tears(draw, frame.tears, self.rx, frame.eye_y)
        self.disp.image(img.rotate(90, expand=True))

    # ── Generator factory ──────────────────────────────────────────────────────

    def _make_gen(self, request):
        l, r, c, m = self._cur_l, self._cur_r, self._cur_c, self._mood
        kind       = request["kind"]

        if kind == "startup":
            return gen_startup()

        if kind == "mood":
            self._mood        = request["mood"]
            self._idle_timers = _IdleTimers()
            print(f"[Eyes] Mood → {self._mood}")
            return gen_idle_settle(l, r, c, self._mood)

        gen = _build_generator(kind, l, r, c, m)
        if gen:
            print(f"[Eyes] Playing → {kind}")
            return gen

        print(f"[Eyes] Unknown animation '{kind}', falling back to idle")
        return gen_idle_cycle(self._mood, self._idle_timers)

    # ── Engine loop ────────────────────────────────────────────────────────────

    def _engine(self):
        gen     = self._make_gen({"kind": "startup"})
        in_idle = False
        print("[Eyes] Engine running")

        while self._running:
            try:
                frame = next(gen)
                self._push(frame)
                time.sleep(cfg.FRAME_DT)

            except StopIteration:
                pending = None
                try:
                    pending = self._queue.get_nowait()
                except queue.Empty:
                    pass

                if pending is not None:
                    in_idle = False
                    gen     = self._make_gen(pending)
                else:
                    if not in_idle:
                        in_idle = True
                        print(f"[Eyes] Entering idle (mood: {self._mood})")
                        gen = gen_idle_settle(
                            self._cur_l, self._cur_r,
                            self._cur_c, self._mood)
                    else:
                        gen = gen_idle_cycle(self._mood, self._idle_timers)

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self):
        self._running = True
        self._thread  = threading.Thread(
            target=self._engine, name="EyeEngine", daemon=True)
        self._thread.start()
        print("[Eyes] Thread started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self.disp.image(Image.new("RGB", (self.W, self.H), cfg.COL_BG))
        print("[Eyes] Stopped")

    def _drain(self):
        try:
            self._queue.get_nowait()
            print("[Eyes] Replaced pending queue item")
        except queue.Empty:
            pass

    def play(self, animation: str):
        if animation not in VALID_ANIMATIONS:
            print(f"[Eyes] Unknown animation '{animation}'")
            return
        self._drain()
        self._queue.put({"kind": animation})
        print(f"[Eyes] Queued → {animation}")

    def set_mood(self, mood: str):
        if mood not in MOOD_STATES:
            print(f"[Eyes] Unknown mood '{mood}'")
            return
        self._drain()
        self._idle_timers = _IdleTimers()
        self._queue.put({"kind": "mood", "mood": mood})
        print(f"[Eyes] Mood queued → {mood}")
