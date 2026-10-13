"""
Voice -> Robot (simulated) backend.

Flow:
  1. Browser records audio, POSTs it to /api/transcribe
     -> we send it to Groq Whisper (whisper-large-v3) and return the text.
  2. Browser POSTs that text to /api/command
     -> we send it to a Groq LLM with a fixed set of "robot tools"
        (move, turn, stop). The LLM must respond using tool calls only.
     -> we validate + clamp every tool call against safety limits,
        update an in-memory virtual robot pose, and return the list
        of executed actions + the new pose to the browser.
  3. Browser animates a robot icon on a <canvas> based on the actions.

No ROS / Gazebo involved - the "robot" is just an (x, y, heading) point
living in server memory, which is exactly the kind of stand-in the
project's own docs describe as a future-proof separation between the
cognitive layer (LLM) and the execution layer (here: a tiny fake robot
instead of ROS 2).
"""

import base64
import json
import math
import os
import threading
import time

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY is not set. Create a .env file or set the environment "
        "variable before starting the server (see README.md)."
    )

client = Groq(api_key=GROQ_API_KEY)

STT_MODEL = "whisper-large-v3"
LLM_MODEL = "openai/gpt-oss-120b"

# Safety limits (mirrors the "safety layer" idea in your project write-up)
MAX_DISTANCE_M = 5.0        # a single move can't exceed this
MAX_TURN_DEG = 180.0        # a single turn can't exceed this
MIN_DISTANCE_M = 0.05
MIN_TURN_DEG = 1.0

# ---------------------------------------------------------------------------
# "Robot" state - a stand-in for the real ROS 2 / Gazebo robot
# ---------------------------------------------------------------------------

robot_state = {"x": 0.0, "y": 0.0, "heading_deg": 0.0, "battery": 100}


# Everything the robot has physically done since the last reset, as primitive
# move/turn actions. "come back" and "undo" replay this in reverse, which
# cancels the car's systematic timing errors far better than computing a
# straight line from an estimated position.
path_log: list[dict] = []
command_starts: list[int] = []   # index into path_log where each command began


def reset_robot():
    robot_state.update({"x": 0.0, "y": 0.0, "heading_deg": 0.0, "battery": 100})
    path_log.clear()
    command_starts.clear()


HIGH_LEVEL = {"return_to_start", "undo", "draw_polygon", "run_plan"}
MAX_ACTIONS = 24  # cap on how many steps one spoken command may expand to
MAX_ROUNDS = 26   # cap on LLM <-> tool round trips per command


def _signed_turn(delta: float) -> list:
    """Shortest turn for a heading change of `delta` degrees (+ = right)."""
    delta = ((delta + 180.0) % 360.0) - 180.0
    if abs(delta) < MIN_TURN_DEG:
        return []
    return [("turn", {"direction": "right" if delta > 0 else "left", "degrees": abs(delta)})]


def _compress(entries: list[dict]) -> list[dict]:
    """Merge adjacent moves (net signed distance) and adjacent turns (net
    signed angle, wrapped) so 4 x left 90 becomes nothing and forward 1 +
    backward 1 cancels."""
    out: list[tuple[str, float]] = []
    for e in entries:
        if e["tool"] == "move":
            kind = "move"
            val = e["distance_m"] if e["direction"] == "forward" else -e["distance_m"]
        elif e["tool"] == "turn":
            kind = "turn"
            val = e["degrees"] if e["direction"] == "right" else -e["degrees"]
        else:
            continue
        if out and out[-1][0] == kind:
            out[-1] = (kind, out[-1][1] + val)
        else:
            out.append((kind, val))

    steps = []
    for kind, val in out:
        if kind == "turn":
            val = ((val + 180.0) % 360.0) - 180.0
            if abs(val) < 0.5:
                continue
        elif abs(val) < 0.005:
            continue
        steps.append((kind, val))
    return steps


def _inverse_steps(entries: list[dict]) -> list:
    """Steps that undo `entries` (a list of executed actions): net each run,
    then play it back in reverse with every direction flipped. The steps are
    marked record=False so the replay itself is not written to the path log."""
    steps = []
    for kind, val in reversed(_compress(entries)):
        if kind == "move":
            remaining = abs(val)
            direction = "backward" if val > 0 else "forward"
            while remaining > 1e-6:
                chunk = min(remaining, MAX_DISTANCE_M)
                steps.append(("move", {"direction": direction, "distance_m": chunk}, False))
                remaining -= chunk
        else:
            direction = "left" if val > 0 else "right"
            steps.append(("turn", {"direction": direction, "degrees": abs(val)}, False))
    return steps


def plan_undo() -> list:
    """Inverse of the last command that actually moved the robot."""
    while command_starts and command_starts[-1] >= len(path_log):
        command_starts.pop()
    if not command_starts:
        return []
    start = command_starts.pop()
    last = path_log[start:]
    del path_log[start:]
    return _inverse_steps(last)


def plan_backtrack() -> list:
    """Retrace everything done since the last reset, in reverse."""
    if not path_log:
        return plan_return_to_start()  # nothing recorded: use the pose estimate
    steps = _inverse_steps(list(path_log))
    path_log.clear()
    command_starts.clear()
    return steps


def plan_polygon(args: dict) -> list:
    """Exact move/turn steps for a regular polygon (n sides, side length)."""
    try:
        n = int(args.get("sides", 4))
    except (TypeError, ValueError):
        n = 4
    n = max(3, min(n, 12))
    try:
        side = float(args.get("side_length_m", 0.5))
    except (TypeError, ValueError):
        side = 0.5
    side = max(MIN_DISTANCE_M, min(abs(side), MAX_DISTANCE_M))
    direction = "left" if args.get("direction") == "left" else "right"
    steps = []
    for _ in range(n):
        steps.append(("move", {"direction": "forward", "distance_m": side}))
        steps.append(("turn", {"direction": direction, "degrees": 360.0 / n}))
    return steps


def expand_tool(name: str, args: dict) -> list:
    """Turn a high-level tool call into the primitive steps that carry it out."""
    if name == "return_to_start":
        return plan_backtrack()
    if name == "undo":
        return plan_undo()
    if name == "draw_polygon":
        return plan_polygon(args)
    if name == "run_plan":
        steps = []
        for entry in args.get("steps") or []:
            if isinstance(entry, dict) and entry.get("action"):
                steps.append((entry["action"], {k: v for k, v in entry.items() if k != "action"}))
        return steps
    return [(name, args)]


def plan_return_to_start() -> list:
    """Steps that take the robot from its tracked pose back to the origin and
    leave it facing its original heading (0 deg): turn toward the origin, drive
    there, turn back to the original heading."""
    x, y, h = robot_state["x"], robot_state["y"], robot_state["heading_deg"]
    dist = math.hypot(x, y)
    if dist < MIN_DISTANCE_M:
        return _signed_turn(-h)

    target = math.degrees(math.atan2(-y, -x))  # direction from robot to origin
    steps = _signed_turn(target - h)
    remaining = dist
    while remaining > 1e-6:
        step = min(remaining, MAX_DISTANCE_M)
        steps.append(("move", {"direction": "forward", "distance_m": step}))
        remaining -= step
    steps += _signed_turn(0.0 - target)
    return steps


# ---------------------------------------------------------------------------
# Tool ("function") definitions given to the LLM
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "move",
            "description": (
                "Drive the robot in a straight line, forward or backward, "
                "by a distance in metres."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["forward", "backward"],
                    },
                    "distance_m": {
                        "type": "number",
                        "description": "Distance to travel, in metres.",
                    },
                },
                "required": ["direction", "distance_m"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "turn",
            "description": "Rotate the robot in place, left or right, by an angle in degrees.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["left", "right"]},
                    "degrees": {
                        "type": "number",
                        "description": "Angle to rotate, in degrees.",
                    },
                },
                "required": ["direction", "degrees"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop",
            "description": "Immediately stop all robot motion.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_position",
            "description": "Get the robot's current x, y position and heading.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_battery",
            "description": "Get the robot's current battery percentage.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_plan",
            "description": (
                "Run an ordered list of steps in ONE call. Use this whenever the "
                "user's instruction has two or more steps (e.g. 'go straight, "
                "then left, then back'). Steps run in the given order."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["move", "turn", "return_to_start"],
                                },
                                "direction": {
                                    "type": "string",
                                    "enum": ["forward", "backward", "left", "right"],
                                    "description": "forward/backward for move, left/right for turn.",
                                },
                                "distance_m": {"type": "number"},
                                "degrees": {"type": "number"},
                            },
                            "required": ["action"],
                        },
                    }
                },
                "required": ["steps"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draw_polygon",
            "description": (
                "Drive a regular polygon path and finish where it started, "
                "facing the original way: square (sides=4), triangle (3), "
                "pentagon (5), hexagon (6). For a circle use sides=12 with a "
                "small side length. The server generates every step exactly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sides": {"type": "integer", "description": "Number of sides, 3 to 12."},
                    "side_length_m": {
                        "type": "number",
                        "description": "Length of each side in metres (default 0.5).",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["right", "left"],
                        "description": "Which way to turn at each corner (default right).",
                    },
                },
                "required": ["sides"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "undo",
            "description": (
                "Undo the robot's previous movement command by doing the exact "
                "inverse (forward 1 m becomes backward 1 m, left 90 becomes "
                "right 90). Use for 'undo', 'undo that', 'take that back', "
                "'reverse the last command'. Can be called repeatedly."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "return_to_start",
            "description": (
                "Drive the robot back to the place it started (its origin) and "
                "face its original direction. Use for 'come back', 'come back "
                "to me', 'return', 'go home', 'go back to the start' when no "
                "distance is given. The server works out the route itself."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

SYSTEM_PROMPT = f"""You are the cognitive control layer for a simulated mobile robot.

You NEVER move the robot yourself and you NEVER write code. You only decide
which of the provided tools to call, with what arguments, to satisfy the
user's spoken or typed instruction.

Rules:
- Always respond using tool calls, not plain text, when the user asks the
  robot to do something.
- A single move() must not exceed {MAX_DISTANCE_M} metres. A single turn()
  must not exceed {MAX_TURN_DEG} degrees. If the user asks for more, split
  it into multiple move()/turn() calls, or clamp to the limit.
- If the instruction is ambiguous (e.g. "go" with no direction or distance),
  make a reasonable default choice: forward, 1 metre, or a 90 degree turn.
- "back", "backward(s)", "reverse", "back up" and "go back <distance>" mean
  move(direction="backward"). Do NOT turn first. Only call turn() when the
  user explicitly says turn, rotate, spin, left, right, or "turn around".
- "come back", "come back to me", "return", "go home", "go back to the start"
  with NO distance mean return_to_start(). The server tracks where the robot
  has been and computes the route, so do not try to reverse moves yourself.
- Shapes: use draw_polygon() for square (sides=4), triangle (3), pentagon (5),
  hexagon (6) and circle (sides=12, small side). Default side is 0.5 metres
  if the user gives none. Never build these out of separate move/turn calls.
  A rectangle or other irregular path: use individual move()/turn() calls.
- For ANY instruction with two or more steps, call run_plan() ONCE with all
  the steps in the order the user said them ("go straight then left then
  back" = steps: move forward, turn left, move backward). "Come back" inside
  a plan is {{"action": "return_to_start"}}. Single steps can be a plain move()
  or turn().
- "undo", "undo that", "take that back", "reverse the last command" mean
  undo(): the server replays the inverse of the previous command exactly.
  This is different from "go back 1 metre", which is a plain backward move.
- Never add turns the user did not ask for.
- If the user asks to stop or cancel, call stop().
- You may call more than one tool in a single response for compound
  instructions such as "go forward then turn left".
- Keep any accompanying text short - it will be read as a status message.
"""



# ---------------------------------------------------------------------------
# Real robot bridge (HC-05 Bluetooth -> Windows COM port -> Arduino)
# ---------------------------------------------------------------------------
# Pair the HC-05 in Windows (PIN 1234 or 0000), find its "Outgoing" COM port in
# Device Manager > Ports, then set ROBOT_PORT=COM5 in .env. Leave it unset to
# keep using the simulated robot only.

ROBOT_PORT = os.environ.get("ROBOT_PORT")
ROBOT_BAUD = int(os.environ.get("ROBOT_BAUD", "9600"))
ROBOT_TIMEOUT_S = 30  # longest we wait for one motion to finish

_robot_serial = None
_robot_lock = threading.Lock()

# --- BLE (HC-08 / HC-10 style modules, no COM port) ------------------------
# Set ROBOT_BLE to the module's advertised name (e.g. HC-08) or its address.
# These modules expose one UART-like characteristic, FFE1, inside service FFE0.

ROBOT_BLE = os.environ.get("ROBOT_BLE")
BLE_CHAR_UUID = os.environ.get("ROBOT_BLE_CHAR", "0000ffe1-0000-1000-8000-00805f9b34fb")

_ble_loop = None
_ble_client = None
_ble_replies = None  # asyncio.Queue of reply lines
_ble_buf = ""


def _ble_loop_get():
    """Background asyncio loop that owns the BLE connection."""
    global _ble_loop
    if _ble_loop is None:
        import asyncio

        _ble_loop = asyncio.new_event_loop()
        threading.Thread(target=_ble_loop.run_forever, daemon=True).start()
    return _ble_loop


async def _ble_ensure_connected():
    global _ble_client, _ble_replies, _ble_buf
    import asyncio
    from bleak import BleakClient, BleakScanner

    if _ble_client is not None and _ble_client.is_connected:
        return
    _ble_replies = asyncio.Queue()
    _ble_buf = ""

    target = ROBOT_BLE.lower()
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: target in ((d.name or ad.local_name or "").lower(), d.address.lower())
        or target in (d.name or ad.local_name or "").lower(),
        timeout=10.0,
    )
    if device is None:
        raise RuntimeError(
            f"BLE device '{ROBOT_BLE}' not found. Is the car on and not connected to a phone?"
        )

    def on_notify(_, data: bytearray):
        global _ble_buf
        _ble_buf += data.decode(errors="ignore")
        while "\n" in _ble_buf:
            line, _ble_buf = _ble_buf.split("\n", 1)
            line = line.strip()
            if line:
                _ble_replies.put_nowait(line)

    client = BleakClient(device)
    await client.connect()
    await client.start_notify(BLE_CHAR_UUID, on_notify)
    _ble_client = client


async def _ble_send(cmd: str) -> str:
    import asyncio

    await _ble_ensure_connected()
    while not _ble_replies.empty():  # drop stale lines
        _ble_replies.get_nowait()
    data = (cmd + "\n").encode()
    for i in range(0, len(data), 20):  # default BLE payload is 20 bytes
        await _ble_client.write_gatt_char(BLE_CHAR_UUID, data[i : i + 20], response=False)

    deadline = time.time() + ROBOT_TIMEOUT_S
    last = ""
    while time.time() < deadline:
        try:
            line = await asyncio.wait_for(_ble_replies.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        last = line
        if line != "OK":
            return line
    return last or "TIMEOUT"


def _send_ble(cmd: str) -> str:
    import asyncio

    global _ble_client
    try:
        fut = asyncio.run_coroutine_threadsafe(_ble_send(cmd), _ble_loop_get())
        return fut.result(timeout=ROBOT_TIMEOUT_S + 20)
    except Exception as exc:
        _ble_client = None  # force a fresh connect next time
        return f"LINK_ERROR: {exc}"


def send_to_robot(cmd: str) -> str:
    """Send one command line to the Arduino and wait for its final reply
    (DONE / BLOCKED n / STOPPED / ERR). Returns the reply, or an error string."""
    global _robot_serial
    if ROBOT_BLE:
        with _robot_lock:
            return _send_ble(cmd)

    import serial  # pyserial

    with _robot_lock:
        try:
            if _robot_serial is None or not _robot_serial.is_open:
                _robot_serial = serial.Serial(ROBOT_PORT, ROBOT_BAUD, timeout=0.5)
                time.sleep(2.0)  # a USB connection resets the Uno; let it boot
            ser = _robot_serial
            ser.reset_input_buffer()
            ser.write((cmd + "\n").encode())
            deadline = time.time() + ROBOT_TIMEOUT_S
            last = ""
            while time.time() < deadline:
                line = ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue
                last = line
                if line != "OK":  # OK just means "started"
                    return line
            return last or "TIMEOUT"
        except Exception as exc:
            _robot_serial = None
            return f"LINK_ERROR: {exc}"

# ---------------------------------------------------------------------------
# Tool execution against the virtual robot
# ---------------------------------------------------------------------------

def to_arduino(action: dict) -> str | None:
    """Encode a validated action as the one-line serial command the Arduino
    sketch will parse (sent over the HC-05 once hardware exists).

    F<cm> / B<cm>  drive forward / backward   L<deg> / R<deg>  turn   S  stop
    """
    tool = action["tool"]
    if tool == "move":
        return f"{'F' if action['direction'] == 'forward' else 'B'}{round(action['distance_m'] * 100)}"
    if tool == "turn":
        return f"{'L' if action['direction'] == 'left' else 'R'}{round(action['degrees'])}"
    if tool == "stop":
        return "S"
    return None


def execute_tool(name: str, args: dict) -> dict:
    """Apply a validated tool call and return an action record (with its Arduino command)."""
    action = _execute_tool(name, args)
    cmd = to_arduino(action)
    if cmd:
        action["arduino"] = cmd
        if ROBOT_BLE or ROBOT_PORT:
            action["robot_reply"] = send_to_robot(cmd)
    return action


def _execute_tool(name: str, args: dict) -> dict:
    """Apply a validated tool call to robot_state and return an action record."""

    if name == "move":
        direction = args.get("direction", "forward")
        distance = float(args.get("distance_m", 1.0))
        distance = max(MIN_DISTANCE_M, min(abs(distance), MAX_DISTANCE_M))
        sign = 1 if direction == "forward" else -1

        heading_rad = math.radians(robot_state["heading_deg"])
        robot_state["x"] += sign * distance * math.cos(heading_rad)
        robot_state["y"] += sign * distance * math.sin(heading_rad)
        robot_state["battery"] = max(0, robot_state["battery"] - round(distance))

        return {
            "tool": "move",
            "direction": direction,
            "distance_m": round(distance, 3),
            "resulting_pose": dict(robot_state),
        }

    if name == "turn":
        direction = args.get("direction", "left")
        degrees = float(args.get("degrees", 90))
        degrees = max(MIN_TURN_DEG, min(abs(degrees), MAX_TURN_DEG))
        sign = -1 if direction == "left" else 1  # standard math angle convention

        robot_state["heading_deg"] = (robot_state["heading_deg"] + sign * degrees) % 360
        robot_state["battery"] = max(0, robot_state["battery"] - 1)

        return {
            "tool": "turn",
            "direction": direction,
            "degrees": round(degrees, 2),
            "resulting_pose": dict(robot_state),
        }

    if name == "stop":
        return {"tool": "stop", "resulting_pose": dict(robot_state)}

    if name == "get_position":
        return {"tool": "get_position", "resulting_pose": dict(robot_state)}

    if name == "get_battery":
        return {"tool": "get_battery", "battery": robot_state["battery"]}

    raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Voice -> Simulated Robot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CommandRequest(BaseModel):
    text: str


@app.get("/")
def index():
    return FileResponse(os.path.join("static", "index.html"))


@app.get("/api/state")
def get_state():
    return robot_state


@app.post("/api/reset")
def reset():
    reset_robot()
    return robot_state


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Send recorded audio to Groq Whisper and return the transcript."""
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio upload.")

    try:
        transcription = client.audio.transcriptions.create(
            file=(audio.filename or "audio.webm", audio_bytes),
            model=STT_MODEL,
            response_format="text",
        )
    except Exception as exc:  # surfaced to the browser as a readable error
        raise HTTPException(status_code=502, detail=f"Groq STT error: {exc}") from exc

    # response_format="text" -> the SDK returns a plain string
    text = transcription if isinstance(transcription, str) else str(transcription)
    return {"text": text.strip()}


@app.post("/api/command")
def command(req: CommandRequest):
    """Send the transcribed/typed text to the LLM, execute any tool calls."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Empty command text.")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": req.text},
    ]
    log_mark = len(path_log)
    actions = []
    reply_text = ""
    halted = False

    # Agent loop: the model proposes tool calls, we execute them and feed each
    # result back so it can decide the next step, until it stops calling tools.
    for _ in range(MAX_ROUNDS):
        try:
            completion = client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
                max_completion_tokens=2048,
                parallel_tool_calls=True,
                extra_body={"reasoning_effort": "low"},
            )
        except Exception as exc:
            if actions:  # something already ran; report that, not an error
                break
            raise HTTPException(status_code=502, detail=f"Groq LLM error: {exc}") from exc

        message = completion.choices[0].message
        reply_text = message.content or reply_text
        tool_calls = message.tool_calls or []
        if not tool_calls:
            break

        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"},
                    }
                    for c in tool_calls
                ],
            }
        )

        for call in tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            name = call.function.name

            if halted or len(actions) >= MAX_ACTIONS:
                result = {"error": "not executed: the robot was halted or the step limit was reached"}
            else:
                # high-level tools (return_to_start, draw_polygon) expand into
                # several move/turn steps
                steps = [(name, args)]
                results = []
                while steps:
                    step = steps.pop(0)
                    step_name, step_args = step[0], step[1]
                    record = step[2] if len(step) > 2 else True
                    if step_name in HIGH_LEVEL:
                        # expanded lazily so return_to_start sees the pose
                        # reached by the steps before it
                        steps[0:0] = expand_tool(step_name, step_args)
                        continue
                    if len(actions) >= MAX_ACTIONS:
                        break
                    try:
                        action = execute_tool(step_name, step_args)
                    except ValueError as exc:
                        results.append({"error": str(exc)})
                        continue
                    actions.append(action)
                    results.append(action)
                    if record and action["tool"] in ("move", "turn"):
                        path_log.append(action)
                    # hardware refused / link down: don't run the rest blind
                    if action.get("robot_reply", "").startswith(
                        ("BLOCKED", "LINK_ERROR", "TIMEOUT", "STOPPED")
                    ):
                        halted = True
                        break
                if len(results) == 1:
                    result = results[0]
                else:
                    result = {"steps_executed": len(results), "final_pose": dict(robot_state)}
                    if halted:
                        result["halted"] = results[-1].get("robot_reply")

            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)}
            )

        if halted or len(actions) >= MAX_ACTIONS:
            break
        # a self-contained plan has been fully executed: no need for another
        # (slow, rate-limited) LLM round just to word a reply
        if any(c.function.name in HIGH_LEVEL | {"stop"} for c in tool_calls):
            break

    if len(path_log) > log_mark:
        command_starts.append(log_mark)

    if not reply_text:
        if halted and actions:
            reply_text = f"Stopped: {actions[-1].get('robot_reply')}"
        elif actions:
            reply_text = f"Done - {len(actions)} step{'s' if len(actions) != 1 else ''}."
        else:
            reply_text = "Nothing to do."

    return {
        "heard": req.text,
        "reply": reply_text,
        "actions": actions,
        "state": robot_state,
    }


app.mount("/static", StaticFiles(directory="static"), name="static")
