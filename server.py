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


def reset_robot():
    robot_state.update({"x": 0.0, "y": 0.0, "heading_deg": 0.0, "battery": 100})


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
- "back", "backward(s)", "reverse", "go back", "come back" and "move back"
  mean move(direction="backward"). Do NOT turn first. Only call turn() when
  the user explicitly says turn, rotate, spin, left, right, or "turn around".
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

    try:
        completion = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": req.text},
            ],
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.3,
            max_completion_tokens=1024,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Groq LLM error: {exc}") from exc

    message = completion.choices[0].message
    tool_calls = message.tool_calls or []

    actions = []
    for call in tool_calls:
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        try:
            actions.append(execute_tool(name, args))
        except ValueError:
            continue
        # hardware refused / link down: don't run the rest of the plan blind
        reply = actions[-1].get("robot_reply", "")
        if reply.startswith(("BLOCKED", "LINK_ERROR", "TIMEOUT", "STOPPED")):
            break

    return {
        "heard": req.text,
        "reply": message.content or "",
        "actions": actions,
        "state": robot_state,
    }


app.mount("/static", StaticFiles(directory="static"), name="static")
