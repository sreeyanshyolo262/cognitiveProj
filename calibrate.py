"""
Calibrate the car's timed motion.

The car has no encoders, so distance/angle = rate * time + offset. The offset
(start-up lag, coasting) is what makes chained commands drift. This script runs
two test distances and two test angles, asks you what you measured, solves for
rate AND offset, and prints (or writes) the new constants for cognibot.ino.

  1. Stop the server (only one program can hold the Bluetooth link).
  2. Power the car, put it on the floor with ~2 m free ahead and room to spin.
  3. venv\\Scripts\\python calibrate.py            (just prints the numbers)
     venv\\Scripts\\python calibrate.py --write    (also patches cognibot.ino)
  4. Re-upload the sketch (unplug the Bluetooth module while uploading).

Tips: mark the start with tape. Measure distance from the same point on the car
(e.g. front axle). For angles, put two pieces of tape on the floor and compare,
or use a phone compass / protractor app. Fully charged batteries give the most
repeatable result - re-run when the batteries are low.
"""

import re
import sys
from pathlib import Path

import server  # loads .env, gives us send_to_robot()

INO = Path(__file__).parent / "arduino" / "cognibot" / "cognibot.ino"
DIST_TESTS = (50, 150)   # cm
TURN_TESTS = (90, 180)   # degrees


def read_const(src: str, name: str) -> float:
    m = re.search(rf"float\s+{name}\s*=\s*(-?[0-9.]+)\s*;", src)
    if not m:
        sys.exit(f"Could not find {name} in {INO}")
    return float(m.group(1))


def patch_const(src: str, name: str, value: float) -> str:
    return re.sub(
        rf"(float\s+{name}\s*=\s*)(-?[0-9.]+)(\s*;)", rf"\g<1>{value:.3f}\g<3>", src, count=1
    )


def ask_float(prompt: str) -> float:
    while True:
        try:
            return float(input(prompt).strip())
        except ValueError:
            print("  please type a number")


def run_tests(cmd_letter: str, tests, unit: str, rate: float, offset: float):
    """Drive each test, ask for the measurement, return (t, measured) pairs."""
    pairs = []
    for amount in tests:
        input(f"\nPlace the car at its start mark, then press Enter to run {cmd_letter}{amount} ...")
        reply = server.send_to_robot(f"{cmd_letter}{amount}")
        print(f"  car replied: {reply}")
        if not reply.startswith("DONE"):
            sys.exit("The car did not finish normally - fix that first (is it on? path clear?).")
        measured = ask_float(f"  How many {unit} did it really {'travel' if unit == 'cm' else 'turn'}? ")
        t = max(0.0, amount - offset) / rate  # time the firmware used (s)
        pairs.append((t, measured))
    return pairs


def solve(pairs, label: str):
    (t1, m1), (t2, m2) = pairs
    if t2 - t1 <= 0.01:
        sys.exit(f"{label}: the two tests ran for the same time - cannot solve.")
    rate = (m2 - m1) / (t2 - t1)
    if rate <= 0:
        sys.exit(f"{label}: measurements make no sense (longer test went shorter). Re-measure.")
    offset = m1 - rate * t1
    return rate, offset


def main():
    write = "--write" in sys.argv
    if not (server.ROBOT_BLE or server.ROBOT_PORT):
        sys.exit("Set ROBOT_BLE (or ROBOT_PORT) in .env so the script can reach the car.")

    src = INO.read_text(encoding="utf-8")
    cm_rate = read_const(src, "CM_PER_SEC")
    cm_off = read_const(src, "MOVE_OFFSET_CM")
    deg_rate = read_const(src, "DEG_PER_SEC")
    deg_off = read_const(src, "TURN_OFFSET_DEG")
    print(f"Current firmware: CM_PER_SEC={cm_rate} MOVE_OFFSET_CM={cm_off} "
          f"DEG_PER_SEC={deg_rate} TURN_OFFSET_DEG={deg_off}")

    print("\nConnecting to the car ...")
    print("  ping:", server.send_to_robot("P"))

    print("\n=== Distance ===")
    new_cm_rate, new_cm_off = solve(run_tests("F", DIST_TESTS, "cm", cm_rate, cm_off), "distance")

    print("\n=== Turning (right) ===")
    new_deg_rate, new_deg_off = solve(run_tests("R", TURN_TESTS, "degrees", deg_rate, deg_off), "turning")

    print("\n--- New constants for arduino/cognibot/cognibot.ino ---")
    print(f"float CM_PER_SEC      = {new_cm_rate:.3f};")
    print(f"float DEG_PER_SEC     = {new_deg_rate:.3f};")
    print(f"float MOVE_OFFSET_CM  = {new_cm_off:.3f};")
    print(f"float TURN_OFFSET_DEG = {new_deg_off:.3f};")

    if write:
        for name, val in (
            ("CM_PER_SEC", new_cm_rate),
            ("DEG_PER_SEC", new_deg_rate),
            ("MOVE_OFFSET_CM", new_cm_off),
            ("TURN_OFFSET_DEG", new_deg_off),
        ):
            src = patch_const(src, name, val)
        INO.write_text(src, encoding="utf-8")
        print(f"\nWrote the new values to {INO}. Re-upload the sketch.")
    else:
        print("\n(Run with --write to patch the sketch file automatically.)")

    print("\nVerify after uploading: say 'turn right 90 degrees four times' - it should end"
          " facing the way it started - and 'go forward 1 metre then come back'.")


if __name__ == "__main__":
    main()
