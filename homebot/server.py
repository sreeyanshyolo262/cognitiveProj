"""
Cognibot Home — simulated delivery/helper robot in a 3D house, controlled by
voice/text through the same style of LLM tool-calling as the real-robot server.

Run:  venv\\Scripts\\python -m uvicorn homebot.server:app --host 0.0.0.0 --port 8010
Then open http://localhost:8010 for the 3D house view (big screen / laptop),
and point the phone app's server address at this same host:8010.
"""
import json
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

from .world import World

load_dotenv()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set. Create a .env file (see project README).")

client = Groq(api_key=GROQ_API_KEY)
STT_MODEL = "whisper-large-v3"
LLM_MODEL = "openai/gpt-oss-120b"
MAX_ROUNDS = 10

world = World(time_scale=float(os.environ.get("SIM_SPEED", "1.6")))
world.start()

TOOLS = [
    {"type": "function", "function": {
        "name": "navigate_to",
        "description": "Drive autonomously to a room, place, person, or item (it plans a path and avoids obstacles). Rooms: bedroom, bathroom, study, hallway, living_room, kitchen. Places: charging_station, front_door, stove, fridge, kitchen_sink, user, grandpa, dining_table, desk, bookshelf, tv, bathroom_sink, bed. Items: water_bottle, medicine, tv_remote, book, keys, apple (navigates next to wherever the item currently is).",
        "parameters": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}}},
    {"type": "function", "function": {
        "name": "look_at",
        "description": "Raise the camera mast and look. With no target, reports everything currently visible. With a target (e.g. 'milk_pot', 'front_door', 'user', 'tv_remote'), focuses on it and describes it in detail (e.g. exactly how boiled the milk is). You must be close enough / in the right room; if not, navigate_to first.",
        "parameters": {"type": "object", "properties": {"target": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "watch_until_change",
        "description": "Keep watching something (currently supports the milk pot) until its state changes (e.g. starts boiling), up to a time limit, then report. Use for 'watch the milk and tell me when it boils'.",
        "parameters": {"type": "object", "properties": {
            "target": {"type": "string"}, "max_seconds": {"type": "number", "description": "default 60"}},
            "required": ["target"]}}},
    {"type": "function", "function": {
        "name": "pick_up",
        "description": "Pick an item up off a surface or the floor. Must be within reach (navigate_to the item first). Carries up to 2 items.",
        "parameters": {"type": "object", "properties": {"item": {"type": "string"}}, "required": ["item"]}}},
    {"type": "function", "function": {
        "name": "drop_off",
        "description": "Put down / hand over carried item(s). If a person is within reach it hands it to them, otherwise sets it on the nearest low surface. Omit item to drop everything carried.",
        "parameters": {"type": "object", "properties": {"item": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "operate_appliance",
        "description": "Turn the stove or TV on/off, or open/close the front door. Must be close to it (navigate_to first).",
        "parameters": {"type": "object", "properties": {
            "appliance": {"type": "string", "enum": ["stove", "tv", "front_door"]},
            "action": {"type": "string", "enum": ["on", "off", "open", "close"]}},
            "required": ["appliance", "action"]}}},
    {"type": "function", "function": {
        "name": "go_charge",
        "description": "Return to the charging station and dock. Use for 'go charge', 'go home', 'recharge', low battery.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "move", "description": "Small manual nudge forward/backward, not for travelling across rooms (use navigate_to for that).",
        "parameters": {"type": "object", "properties": {
            "direction": {"type": "string", "enum": ["forward", "backward"]}, "distance_m": {"type": "number"}},
            "required": ["direction", "distance_m"]}}},
    {"type": "function", "function": {
        "name": "turn", "description": "Rotate in place.",
        "parameters": {"type": "object", "properties": {
            "direction": {"type": "string", "enum": ["left", "right"]}, "degrees": {"type": "number"}},
            "required": ["direction", "degrees"]}}},
    {"type": "function", "function": {
        "name": "stop", "description": "Immediately stop all motion / cancel the current task.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "get_status",
        "description": "Battery %, current room, docked?, what it's carrying, current task.",
        "parameters": {"type": "object", "properties": {}}}},
]

SYSTEM_PROMPT = """You are the onboard intelligence of Cognibot, an autonomous home helper/delivery
robot in a house with a bedroom, bathroom, study, hallway, living room and
kitchen. You NEVER move the robot yourself and NEVER write code - you only
choose tools, exactly as a real robot's safety-layer architecture requires.

How to work:
- Break the user's request into tool calls and execute them IN ORDER, one
  request per message if needed, reading each tool's result before deciding
  the next step (this is a multi-step agent loop, not single-shot).
- To check on or answer a question about something (e.g. "is the milk
  boiling?", "is grandpa okay?", "what's on the table?"), you must
  navigate_to the right room/place FIRST, then look_at the specific thing.
  Never guess - only report what look_at / watch_until_change actually told
  you.
- "go to the kitchen and check if the milk is boiling" = navigate_to kitchen,
  then look_at milk_pot, then answer using exactly what you saw.
- "watch the milk and tell me when it's boiling" = watch_until_change.
- To deliver/fetch an item: navigate_to the item, pick_up it, navigate_to the
  recipient (or room), drop_off it.
- "go charge" / "go and charge" / battery low -> go_charge.
- If a tool returns ok:false (blocked route, item out of reach, unknown
  place), explain the problem in your reply instead of silently retrying the
  same thing more than once.
- Keep your final spoken reply short and natural, like a helpful assistant
  talking to its owner - report what you actually found/did, not just "done".
"""


class CommandRequest(BaseModel):
    text: str


class ControlRequest(BaseModel):
    action: str
    x: float | None = None
    z: float | None = None


app = FastAPI(title="Cognibot Home")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

HANDLERS = {
    "navigate_to": lambda a: world.navigate(a.get("target", "")),
    "look_at": lambda a: world.look(a.get("target")),
    "watch_until_change": lambda a: world.watch(a.get("target", "milk_pot"), a.get("max_seconds", 60)),
    "pick_up": lambda a: world.pick_up(a.get("item", "")),
    "drop_off": lambda a: world.drop_off(a.get("item")),
    "operate_appliance": lambda a: world.operate(a.get("appliance", ""), a.get("action", "")),
    "go_charge": lambda a: world.go_charge(),
    "move": lambda a: world.move(a.get("direction", "forward"), a.get("distance_m", 0.3)),
    "turn": lambda a: world.turn(a.get("direction", "left"), a.get("degrees", 90)),
    "stop": lambda a: (world.stop(), {"ok": True, "result": "Stopped."})[1],
    "get_status": lambda a: {"ok": True, **world.status()},
}


@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))


@app.get("/api/map")
def api_map():
    return world.static_map()


@app.get("/api/state")
def api_state():
    return world.snapshot()


@app.get("/api/last_result")
def api_last_result():
    return getattr(world, "last_result", None) or {}


@app.post("/api/control")
def api_control(req: ControlRequest):
    return world.control(req.action, req.x, req.z)


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    data = await audio.read()
    if not data:
        raise HTTPException(400, "Empty audio upload.")
    try:
        t = client.audio.transcriptions.create(file=(audio.filename or "a.webm", data),
                                                model=STT_MODEL, response_format="text")
    except Exception as exc:
        raise HTTPException(502, f"Groq STT error: {exc}") from exc
    text = (t if isinstance(t, str) else str(t)).strip()
    if text:
        world.set_heard(text)
    return {"text": text}


@app.post("/api/command")
def command(req: CommandRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(400, "Empty command text.")
    if world.busy:
        raise HTTPException(409, "Still working on the previous command.")

    def work():
        world.busy = True
        world.set_heard(text)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}]
        actions, reply = [], ""
        try:
            for _ in range(MAX_ROUNDS):
                try:
                    c = client.chat.completions.create(model=LLM_MODEL, messages=messages, tools=TOOLS,
                                                        tool_choice="auto", temperature=0.2,
                                                        max_completion_tokens=1024)
                except Exception as exc:
                    reply = reply or f"(LLM error: {exc})"
                    break
                msg = c.choices[0].message
                reply = msg.content or reply
                calls = msg.tool_calls or []
                if not calls:
                    break
                messages.append({"role": "assistant", "content": msg.content or "",
                                  "tool_calls": [{"id": cc.id, "type": "function",
                                                   "function": {"name": cc.function.name,
                                                                "arguments": cc.function.arguments or "{}"}}
                                                  for cc in calls]})
                for cc in calls:
                    try:
                        args = json.loads(cc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    fn = HANDLERS.get(cc.function.name)
                    result = fn(args) if fn else {"ok": False, "error": "unknown tool"}
                    actions.append({"tool": cc.function.name, "args": args, "result": result})
                    messages.append({"role": "tool", "tool_call_id": cc.id, "content": json.dumps(result)})
        finally:
            if not reply:
                reply = "Done." if actions else "I didn't do anything for that."
            world.say(reply)
            world.event(f'"{text}" -> {reply}')
            world.busy = False
        world.last_result = {"heard": text, "reply": reply, "actions": actions}

    threading.Thread(target=work, daemon=True).start()
    return {"accepted": True}


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
