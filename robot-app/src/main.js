import "./style.css";

const $ = (id) => document.getElementById(id);
// Default server address. Set VITE_SERVER_URL in robot-app/.env.local to your
// laptop's Wi-Fi address (see README), or change it in the app's gear menu.
const DEFAULT_SERVER = import.meta.env.VITE_SERVER_URL || "http://localhost:8000";

let server = localStorage.getItem("cognibot.server") || DEFAULT_SERVER;
let connected = false;
let busy = false;
let isSim = false; // true when talking to homebot (the simulated house), not the real car

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
  // real car: {x,y,heading_deg,battery}. sim house: {robot:{x,z,th,battery,room,task,docked}}
  const battery = isSim ? s.robot?.battery : s.battery;
  const pct = Math.max(0, Math.min(100, Math.round(battery ?? 0)));
  $("batText").textContent = pct + "%";
  $("batFill").style.width = pct + "%";
  $("batFill").style.background = pct < 20 ? "var(--bad)" : "var(--ok)";
  if (isSim) {
    const r = s.robot || {};
    $("posText").textContent = r.room || "—";
    $("headText").textContent = r.docked ? "Docked" : cap(r.activity || "idle");
  } else {
    $("posText").textContent = `${s.x.toFixed(2)} m, ${s.y.toFixed(2)} m`;
    $("headText").textContent = `${Math.round(s.heading_deg)}°`;
  }
}

function describe(a) {
  switch (a.tool) {
    case "move": return `${cap(a.direction)} ${a.distance_m} m`;
    case "turn": return `Turn ${a.direction} ${a.degrees}°`;
    case "stop": return "Stop";
    case "get_position": return "Check position";
    case "get_battery": return `Battery ${a.battery}%`;
    case "navigate_to": return `→ ${a.args?.target ?? ""}`.replaceAll("_", " ");
    case "look_at": return a.args?.target ? `👁 Look at ${a.args.target}`.replaceAll("_", " ") : "👁 Look around";
    case "watch_until_change": return `👁 Watch ${a.args?.target ?? ""}`.replaceAll("_", " ");
    case "pick_up": return `Pick up ${a.args?.item ?? ""}`.replaceAll("_", " ");
    case "drop_off": return `Drop off ${a.args?.item ?? ""}`.replaceAll("_", " ");
    case "operate_appliance": return `${cap(a.args?.action ?? "")} ${a.args?.appliance ?? ""}`.replaceAll("_", " ");
    case "go_charge": return "🔋 Go charge";
    case "get_status": return "Status check";
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
      c.className = "chip" + (a.result && a.result.ok === false ? " bad" : "");
      c.textContent = describe(a) + (a.result && a.result.ok === false ? " ✕" : "");
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
    isSim = !!state.robot; // homebot's /api/state has a nested "robot" object
    connected = true;
    $("connectView").hidden = true;
    $("connectedView").hidden = false;
    $("batteryRow").hidden = false;
    $("dock").hidden = false;
    $("heroReal").hidden = isSim;
    $("simView").hidden = !isSim;
    if (isSim) {
      $("simFrame").src = server.replace(/\/+$/, "") + "/";
      startSimPoll();
    }
    $("srvText").textContent = (isSim ? "🏠 Sim — " : "") + server.replace(/^https?:\/\//, "");
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
  stopSimPoll();
  $("connectView").hidden = false;
  $("connectedView").hidden = true;
  $("batteryRow").hidden = true;
  $("dock").hidden = true;
  $("heroReal").hidden = false;
  $("simView").hidden = true;
  $("simFrame").src = "about:blank";
  $("connectHint").className = "hint";
  $("connectHint").textContent = "Make sure the server is running on your laptop.";
  setStatus("", "Offline");
}

// Sim's /api/state changes continuously (robot driving, milk boiling, etc.) —
// poll it to keep the battery/room/task row live even with no command in flight.
let simPollTimer = null;
function startSimPoll() {
  stopSimPoll();
  simPollTimer = setInterval(async () => {
    if (!connected || !isSim) return;
    try { renderState(await api("/api/state", {}, 4000)); } catch { /* transient */ }
  }, 1000);
}
function stopSimPoll() {
  if (simPollTimer) clearInterval(simPollTimer);
  simPollTimer = null;
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
    if (isSim && r.accepted) {
      await pollSimResult(text);
    } else {
      addCard({ heard: r.heard, reply: r.reply, actions: r.actions });
      renderState(r.state);
    }
  } catch (e) {
    addCard({ heard: text, error: e.message });
  } finally {
    setBusy(false);
  }
}

// The sim robot runs each command in the background (navigating across rooms
// takes real time), so /api/command returns instantly and we watch the
// world's "busy" flag, then fetch what actually happened.
async function pollSimResult(text) {
  const deadline = Date.now() + 180000;
  while (Date.now() < deadline) {
    const s = await api("/api/state", {}, 5000);
    renderState(s);
    if (s.speech?.text) setBusy(true, s.robot?.task || "Working…");
    if (!s.busy) break;
    await new Promise((res) => setTimeout(res, 450));
  }
  const r = await api("/api/last_result", {}, 5000);
  addCard({ heard: r.heard || text, reply: r.reply, actions: r.actions || [] });
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
    if (isSim) {
      await api("/api/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "reset" }),
      });
      renderState(await api("/api/state"));
      addCard({ heard: "Reset world", reply: "The house, robot and battery were reset." });
    } else {
      renderState(await api("/api/reset", { method: "POST" }));
      addCard({ heard: "Reset robot to start", reply: "Position and battery reset." });
    }
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
