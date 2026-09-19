// Content script injected into Google Slides. Renders the Heard overlay,
// listens to the user's speech, buffers it into chunks, and asks the backend
// (via the service worker) for live coaching pop-ups.
//
// Transcription strategy:
//   - For a fast hackathon demo we use the browser's Web Speech API to get the
//     transcript client-side, then send text chunks to /feedback/live.
//   - The backend ALSO supports server-side ElevenLabs transcription
//     (/feedback/transcribe) if you'd rather stream raw audio — swap that in
//     by capturing getUserMedia audio and POSTing chunks.

const CHUNK_WORD_THRESHOLD = 18;
let sessionId = null;
let recognition = null;
let wordBuffer = [];

function send(type, payload) {
  return new Promise((resolve) => chrome.runtime.sendMessage({ type, ...payload }, resolve));
}

// ---- Overlay UI ----
function mountOverlay() {
  if (document.getElementById("heard-overlay")) return;
  const el = document.createElement("div");
  el.id = "heard-overlay";
  el.innerHTML = `
    <div class="heard-head">
      <span class="heard-dot"></span> Heard
      <button id="heard-toggle">Start</button>
    </div>
    <div id="heard-tips"></div>
  `;
  document.body.appendChild(el);
  document.getElementById("heard-toggle").addEventListener("click", toggle);
}

function showTip(feedback, category) {
  const tips = document.getElementById("heard-tips");
  const tip = document.createElement("div");
  tip.className = "heard-tip";
  tip.innerHTML = `<b>${category || "tip"}</b> ${feedback}`;
  tips.prepend(tip);
  setTimeout(() => tip.classList.add("fade"), 6000);
  setTimeout(() => tip.remove(), 7000);
}

// ---- Speech capture ----
async function toggle() {
  const btn = document.getElementById("heard-toggle");
  if (recognition) {
    stop();
    btn.textContent = "Start";
    return;
  }

  // Ensure we have an active practice session.
  const { heard_active_session } = await chrome.storage.local.get("heard_active_session");
  if (!heard_active_session) {
    showTip("Open the Heard popup and start a practice run first.", "setup");
    return;
  }
  sessionId = heard_active_session;
  start();
  btn.textContent = "Stop";
}

function start() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    showTip("This browser doesn't support live speech capture.", "setup");
    return;
  }
  recognition = new SR();
  recognition.continuous = true;
  recognition.interimResults = false;
  recognition.lang = "en-US";

  recognition.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const text = event.results[i][0].transcript.trim();
      if (text) wordBuffer.push(...text.split(/\s+/));
    }
    if (wordBuffer.length >= CHUNK_WORD_THRESHOLD) flushChunk();
  };
  recognition.onerror = (e) => showTip(`Mic error: ${e.error}`, "setup");
  recognition.start();
}

async function flushChunk() {
  const chunk = wordBuffer.join(" ");
  wordBuffer = [];
  const res = await send("LIVE_FEEDBACK", { sessionId, text: chunk });
  if (res?.ok) showTip(res.feedback.feedback, res.feedback.tip_category);
}

async function stop() {
  if (recognition) {
    recognition.stop();
    recognition = null;
  }
  if (wordBuffer.length) await flushChunk();
  // Kick off the final summary; the full report lives in the web app.
  const res = await send("SUMMARIZE", { sessionId });
  if (res?.ok) showTip(`Done! Score: ${res.summary.score}/100 — see the web app for details.`, "summary");
}

mountOverlay();
