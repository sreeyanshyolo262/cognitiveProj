# Cognibot Home — simulated delivery/helper robot (no hardware needed)

A fully simulated house (bedroom, bathroom, study, hallway, living room,
kitchen) with a robot that **navigates on its own, perceives things, and
acts** — driven by the same voice/LLM pipeline as the real car. Use this to
demo the project without the Arduino.

```
Phone app (mic/text) → this server → Groq Whisper + Groq LLM (agent loop,
   tool calls: navigate_to, look_at, pick_up, drop_off, operate_appliance,
   go_charge, ...) → simulated robot (A* path planning, physics, obstacle
   avoidance, simulated camera) → 3D house view in the browser (laptop screen)
```

## Run it

```powershell
cd C:\Users\Tanu\Code\cognitiveProject
venv\Scripts\activate
python -m uvicorn homebot.server:app --host 0.0.0.0 --port 8010
```

Uses the same `GROQ_API_KEY` from the project's `.env`.

1. **On the laptop**, open **http://localhost:8010** — this is the 3D house,
   shown on the big screen / projector for your teacher to watch.
2. **On the phone app**, open Settings (gear) → Server, and set it to
   `http://YOUR_LAPTOP_IP:8010` (same Wi-Fi, same IP-finding steps as the
   real robot — see the main README). Tap Connect. The app detects it's
   talking to the simulator and shows a live mini view of the house instead
   of the car photo.

## Say things like

- *"Go to the kitchen and check if the milk is boiling."*
- *"Watch the milk and tell me when it starts boiling."*
- *"Bring me the water bottle."* / *"Take the medicine to Grandpa."*
- *"Turn off the stove."* / *"Turn on the TV."*
- *"Go and charge."* / *"What's your battery?"*
- *"Is the front door open? Go check."*

The robot plans a real path with A*, drives around furniture, and will
**re-plan live** if something blocks its route (see the scenario buttons
below). The LLM never invents what it saw — `look_at` reports the actual
simulated state (exact milk temperature/boiling stage, who's holding what,
etc.) and the LLM just relays it.

## Demo scenario buttons

The 3D view's right panel has buttons to script a demo on the fly:
**milk almost/boiling/cold**, **block the hallway** (robot must re-route),
**open/close the front door**, **battery → low**, **reset world**.

## Notes

- `homebot/world.py` is the whole simulation: map, A* planner, robot physics
  with a simulated ultrasonic-style obstacle stop, a simple field-of-view
  camera model, items/people/appliances. No external game engine.
- `homebot/server.py` exposes it over HTTP with the same tool-calling agent
  pattern as `server.py` (the real-car server) — swapping it back to the real
  robot later is "point the app at the other server", nothing else changes.
- This is independent of the real-robot server/app code — nothing here
  touches `server.py`, `arduino/`, or the phone app's real-robot path.
