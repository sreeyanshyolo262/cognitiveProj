# Voice → Robot (simulated)

A minimal version of your cognitive-robotics pipeline that runs entirely on
Windows with no ROS 2 / Gazebo:

```
Mic → browser recording → Groq Whisper (speech-to-text)
    → Groq LLM with tool calling (move / turn / stop)
    → in-memory "robot" pose → animated on a <canvas> in the browser
```

The LLM never moves the robot directly — it can only call `move()`, `turn()`,
`stop()`, `get_position()`, `get_battery()`. The server validates and clamps
every call (max distance, max turn angle) before applying it, exactly like
the "safety layer" described in your project write-up. Swapping this
in-memory robot for a real ROS 2 / rosbridge connection later only means
changing `execute_tool()` in `server.py` — nothing else in the pipeline
changes.

## 1. Requirements

- Windows 10/11
- Python 3.10+ (https://www.python.org/downloads/) — during install, check
  "Add python.exe to PATH"
- A free Groq API key: https://console.groq.com/keys
- A browser that supports microphone recording (Chrome, Edge, Firefox)

## 2. Setup

Open PowerShell in this project folder and run:

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Set your Groq API key for the current session:

```powershell
$env:GROQ_API_KEY = "your_groq_api_key_here"
```

(To avoid retyping it every time, you can instead set it permanently via
Windows "Environment Variables" settings, or create a `.env` file — see the
note at the bottom.)

## 3. Run

```powershell
uvicorn server:app --reload
```

Then open **http://localhost:8000** in your browser.

- Click and hold **"Hold to talk to the robot"**, say something like
  *"move forward one metre"* or *"turn left ninety degrees, then move
  forward two metres"*, and release.
- Or just type a command in the text box and hit Send.
- Watch the green triangle move on the grid — that's your simulated robot.
  Its trail, position, heading and a fake battery level are all tracked.
- "Reset robot" puts it back at the origin.

## 4. Try these commands

- "Go forward about a metre."
- "Turn right ninety degrees."
- "Move forward two metres and then turn left."
- "Stop."
- "Where are you?" (calls `get_position`)
- "What's your battery level?"

## 5. Project structure

```
voice-robot-project/
├── server.py          FastAPI backend: /api/transcribe, /api/command, /api/state, /api/reset
├── requirements.txt
├── static/
│   └── index.html     Recording button + canvas robot + command log (all JS, no build step)
└── README.md
```

## 6. Notes / things to adjust

- **Model names**: the backend uses `whisper-large-v3` for speech-to-text and
  `openai/gpt-oss-120b` for reasoning/tool-calling (matching the example you
  gave). Change `STT_MODEL` / `LLM_MODEL` at the top of `server.py` if you
  want to try a different Groq model.
- **Safety limits**: `MAX_DISTANCE_M` and `MAX_TURN_DEG` in `server.py` cap
  any single move/turn — tune these to match what you want to claim in your
  report.
- **`.env` file instead of an env var**: if you'd rather not set
  `GROQ_API_KEY` every session, `pip install python-dotenv`, add
  `from dotenv import load_dotenv; load_dotenv()` near the top of
  `server.py`, and create a `.env` file containing
  `GROQ_API_KEY=your_key_here` in this folder.
- **Multiple users**: the robot pose is a single global variable for
  simplicity (one shared robot). For a multi-user demo you'd key
  `robot_state` by a session id instead.
- **Moving to real ROS 2 later**: keep everything upstream of
  `execute_tool()` identical; inside `execute_tool()`, instead of updating
  `robot_state`, publish the corresponding `Twist` message to `/cmd_vel` via
  rosbridge, exactly as described in your original architecture doc.
