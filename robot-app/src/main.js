import "./style.css";

const $ = (id) => document.getElementById(id);
// Laptop's Wi-Fi address (works from the phone and on the laptop itself).
// Change it in the gear menu if your network/IP changes.
const DEFAULT_SERVER = "http://10.120.225.170:8000";

let server = localStorage.getItem("cognibot.server") || DEFAULT_SERVER;
let connected = false;
let busy = false;

// ---------- helpers ----------

const api = async (path, opts = {}, timeoutMs = 20000) => {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(server.replace(/\/+$/, "") + path, { ...opts, signal: ctrl.signal });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    return await res.json();
  } catch (e) {
    if (e.name === "AbortError") throw new Error("Server timed out");
    throw e;
  } finally {
    clearTimeout(t);
  }
};

const setStatus = (kind, text) => {
  $("status").className = "status " + kind;
  $("statusText").textContent = text;
};

const setBusy = (b, label) => {
  busy = b;
  $("sendBtn").disabled = b;
  $("cmdInput").disabled = b;
  if (b) setStatus("busy", label || "Working…");
  else if (connected) setStatus("on", "Connected");
};

function renderState(s) {
  if (!s) return;
  const pct = Math.max(0, Math.min(100, Math.round(s.battery ?? 0)));
  $("batText").textContent = pct + "%";
  $("batFill").style.width = pct + "%";
  $("batFill").style.background = pct < 20 ? "var(--bad)" : "var(--ok)";
  $("posText").textContent = `${s.x.toFixed(2)} m, ${s.y.toFixed(2)} m`;
  $("headText").textContent = `${Math.round(s.heading_deg)}°`;
}

function describe(a) {
  switch (a.tool) {
    case "move": return `${cap(a.direction)} ${a.distance_m} m`;
    case "turn": return `Turn ${a.direction} ${a.degrees}°`;
    case "stop": return "Stop";
    case "get_position": return "Check position";
    case "get_battery": return `Battery ${a.battery}%`;
    default: return a.tool;
  }
}
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function addCard({ heard, reply, actions = [], error }) {
  const log = $("log");
  log.querySelector(".empty")?.remove();
  const card = document.createElement("div");
  card.className = "card";

  const h = document.createElement("div");
  h.className = "heard";
  h.textContent = `“${heard}”`;
  card.appendChild(h);

  if (reply) {
    const r = document.createElement("div");
    r.className = "reply";
    r.textContent = reply;
    card.appendChild(r);
  }
  if (error) {
    const e = document.createElement("div");
    e.className = "err";
    e.textContent = error;
    card.appendChild(e);
  }
  if (actions.length) {
    const chips = document.createElement("div");
    chips.className = "chips";
    actions.forEach((a) => {
      const c = document.createElement("span");
      c.className = "chip";
      c.textContent = describe(a);
      chips.appendChild(c);
    });
    card.appendChild(chips);

    const wire = actions.map((a) => a.arduino).filter(Boolean);
    if (wire.length) {
      const w = document.createElement("div");
      w.className = "wire";
      const l = document.createElement("span");
      l.className = "lbl";
      l.textContent = "Sent to Arduino";
      w.appendChild(l);
      w.appendChild(document.createTextNode(wire.join("\n")));
      card.appendChild(w);
    }
  } else if (!error && !reply) {
    const r = document.createElement("div");
    r.className = "reply";
    r.textContent = "No action taken.";
    card.appendChild(r);
  }
  log.prepend(card);
}

function resetLog() {
  $("log").innerHTML = '<div class="empty">Say or type something like “go forward 2 metres, then turn left”.</div>';
}

// ---------- connection ----------

async function connect() {
  const btn = $("connectBtn");
  btn.disabled = true;
  btn.textContent = "Connecting…";
  setStatus("busy", "Connecting…");
  $("connectHint").className = "hint";
  try {
    const state = await api("/api/state", {}, 6000);
    connected = true;
    $("connectView").hidden = true;
    $("connectedView").hidden = false;
    $("batteryRow").hidden = false;
    $("dock").hidden = false;
    $("srvText").textContent = server.replace(/^https?:\/\//, "");
    setStatus("on", "Connected");
    renderState(state);
  } catch (e) {
    setStatus("err", "Offline");
    $("connectHint").className = "hint err";
    $("connectHint").textContent =
      `Couldn't reach ${server}. Check the server is running, the phone is on the same Wi-Fi, ` +
      `and the address in Settings (gear) is your laptop's IP, not localhost. (${e.message})`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Connect";
  }
}

function disconnect() {
  connected = false;
  $("connectView").hidden = false;
  $("connectedView").hidden = true;
  $("batteryRow").hidden = true;
  $("dock").hidden = true;
  $("connectHint").className = "hint";
  $("connectHint").textContent = "Make sure the server is running on your laptop.";
  setStatus("", "Offline");
}

// ---------- commands ----------

async function sendCommand(text) {
  text = text.trim();
  if (!text || busy) return;
  setBusy(true, "Thinking…");
  try {
    const r = await api("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    addCard({ heard: r.heard, reply: r.reply, actions: r.actions });
    renderState(r.state);
  } catch (e) {
    addCard({ heard: text, error: e.message });
  } finally {
    setBusy(false);
  }
}

$("cmdForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = $("cmdInput").value;
  $("cmdInput").value = "";
  sendCommand(v);
});

$("stopBtn").onclick = () => sendCommand("stop");
$("batteryBtn").onclick = () => sendCommand("what's your battery level?");
$("resetBtn").onclick = async () => {
  try {
    renderState(await api("/api/reset", { method: "POST" }));
    addCard({ heard: "Reset robot to start", reply: "Position and battery reset." });
  } catch (e) {
    addCard({ heard: "Reset", error: e.message });
  }
};
$("disconnectBtn").onclick = disconnect;
$("clearBtn").onclick = resetLog;

// ---------- voice (hold to talk) ----------

let recorder = null;
let chunks = [];
let stream = null;
let recStart = 0;

async function startRec() {
  if (busy || recorder) return;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    $("live").textContent = "Microphone permission denied.";
    return;
  }
  chunks = [];
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  recorder.onstop = onRecStop;
  recorder.start();
  recStart = Date.now();
  $("micBtn").classList.add("rec");
  $("live").textContent = "Listening…";
}

function stopRec() {
  if (recorder && recorder.state !== "inactive") recorder.stop();
}

async function onRecStop() {
  const mime = recorder.mimeType || "audio/webm";
  const tooShort = Date.now() - recStart < 400;
  stream?.getTracks().forEach((t) => t.stop());
  recorder = null;
  $("micBtn").classList.remove("rec");

  if (tooShort || !chunks.length) {
    $("live").textContent = "Hold the mic a bit longer.";
    setTimeout(() => ($("live").textContent = ""), 1800);
    return;
  }

  const blob = new Blob(chunks, { type: mime });
  const ext = mime.includes("mp4") ? "m4a" : mime.includes("ogg") ? "ogg" : "webm";
  const fd = new FormData();
  fd.append("audio", blob, `command.${ext}`);

  setBusy(true, "Transcribing…");
  $("live").textContent = "Transcribing…";
  try {
    const { text } = await api("/api/transcribe", { method: "POST", body: fd });
    $("live").textContent = text ? `“${text}”` : "";
    setBusy(false);
    if (text) await sendCommand(text);
    else $("live").textContent = "Didn't catch that.";
  } catch (e) {
    setBusy(false);
    addCard({ heard: "Voice command", error: e.message });
  } finally {
    setTimeout(() => ($("live").textContent = ""), 2500);
  }
}

const mic = $("micBtn");
mic.addEventListener("pointerdown", (e) => { e.preventDefault(); mic.setPointerCapture(e.pointerId); startRec(); });
mic.addEventListener("pointerup", stopRec);
mic.addEventListener("pointercancel", stopRec);
mic.addEventListener("contextmenu", (e) => e.preventDefault());

// ---------- settings ----------

$("settingsBtn").onclick = () => {
  $("serverInput").value = server;
  $("settings").showModal();
};
$("settings").addEventListener("close", () => {
  if ($("settings").returnValue !== "ok") return;
  const v = $("serverInput").value.trim();
  if (v) {
    server = v;
    localStorage.setItem("cognibot.server", v);
    if (connected) disconnect();
  }
});

$("connectBtn").onclick = connect;
resetLog();
