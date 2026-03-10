# main.py
# ─────────────────────────────────────────────────────────────────────────────
# Entry point. Wires together controller, sensors, and audio.
#
# To add a new sensor:
#   1. Import it
#   2. Instantiate it with:  MySensor(on_event=controller.handle_event)
#   3. Register it:          controller.register_sensor(my_sensor)
#   Done. No other file needs to change.
# ─────────────────────────────────────────────────────────────────────────────

from controller import Controller
from animations.sensors.touch import TouchSensor
from animations.audio.listener import MicListener   # stub until mic is connected

# ── Build controller ──────────────────────────────────────────────────────────

controller = Controller()

# ── Register sensors ──────────────────────────────────────────────────────────

touch = TouchSensor(on_event=controller.handle_event)
controller.register_sensor(touch)

# Uncomment when mic hardware is connected:
# mic = MicListener(on_event=controller.handle_event)
# controller.register_sensor(mic)

# ── Start everything ──────────────────────────────────────────────────────────

controller.start()

# ── CLI for manual testing ────────────────────────────────────────────────────

print("\n─── RoboEyes Controller ─────────────────────────────")
print("Touch sensor active on GPIO17.")
print()
print("  Tap          → surprised")
print("  Double-tap   → happy")
print("  Rub          → laugh")
print("  Hold         → sad")
print()
print("Manual commands:")
print("  play <anim>   blink, look_left, look_right, look_up, look_down,")
print("                happy, angry, sad, surprised, tired, laugh, confused")
print("  mood <name>   default, happy, angry, sad, tired, surprised")
print("  q             quit")
print("─────────────────────────────────────────────────────\n")

try:
    while True:
        try:
            cmd = input("> ").strip().lower()
        except EOFError:
            break

        if cmd == "q":
            break
        elif cmd.startswith("play "):
            controller.play(cmd[5:].strip())
        elif cmd.startswith("mood "):
            controller.set_mood(cmd[5:].strip())
        elif cmd == "help":
            print("  play <anim> | mood <name> | q")
        elif cmd == "":
            pass
        else:
            print("  Unknown command. Type 'help'.")

except KeyboardInterrupt:
    pass

finally:
    print("\nShutting down...")
    controller.stop()
    print("Goodbye.")
