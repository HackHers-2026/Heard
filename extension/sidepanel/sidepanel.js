// Side panel: request mic access, capture audio, stream 16kHz PCM to the backend
// over a WebSocket, and render the live transcript coming back from ElevenLabs.
//
// WHERE THE TRANSCRIPT LIVES (this step):
//   - Live, in this panel's memory (`finalText` + `interimText`) and rendered in
//     the DOM as it streams.
//   - Mirrored to chrome.storage.session so it survives closing/reopening the
//     panel or switching tabs during the browser session.
//   - It is NOT written to the backend database yet — persisting a finished
//     transcript to the DB is a later step.
import { STT_WS_URL, SAMPLE_RATE } from "../src/config.js";

const els = {
  start: document.getElementById("start"),
  stop: document.getElementById("stop"),
  clear: document.getElementById("clear"),
  status: document.getElementById("status"),
  transcript: document.getElementById("transcript"),
  conn: document.getElementById("conn"),
  meter: document.getElementById("meter"),
};

const STORAGE_KEY = "heard_live_transcript";
const FLUSH_MS = 200; // send audio to the backend ~5x/second

let ws = null;
let audioContext = null;
let workletNode = null;
let sourceNode = null;
let mediaStream = null;
let pending = []; // Float32 chunks awaiting flush
let flushTimer = null;

let finalText = "";
let interimText = "";

// ---- boot: restore any transcript captured earlier this session ----
init();
async function init() {
  const saved = await chrome.storage.session.get(STORAGE_KEY);
  finalText = saved[STORAGE_KEY] || "";
  render();
  els.meter.innerHTML = "<i></i>";
}

els.start.addEventListener("click", start);
els.stop.addEventListener("click", stop);
els.clear.addEventListener("click", async () => {
  finalText = "";
  interimText = "";
  await chrome.storage.session.remove(STORAGE_KEY);
  render();
});

// ---------------------------------------------------------------------------
// Recording lifecycle
// ---------------------------------------------------------------------------
async function start() {
  setStatus("Requesting microphone…");
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
  } catch (err) {
    setStatus(`Microphone blocked: ${err.name}. Allow mic access for this extension.`);
    return;
  }

  openSocket();
  await startAudioGraph();

  els.start.disabled = true;
  els.stop.disabled = false;
  setStatus("Listening… speak naturally.");
}

async function stop() {
  els.stop.disabled = true;
  stopAudioGraph();

  // Commit any straggling interim text, then close the socket.
  if (interimText.trim()) {
    finalText = joinText(finalText, interimText);
    interimText = "";
    persist();
    render();
  }
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "stop" }));
    ws.close();
  }
  ws = null;
  setConn(false);
  els.start.disabled = false;
  setStatus("Stopped. Transcript saved for this session.");
}

// ---------------------------------------------------------------------------
// WebSocket to backend (which proxies ElevenLabs Scribe realtime v2)
// ---------------------------------------------------------------------------
function openSocket() {
  ws = new WebSocket(STT_WS_URL);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    setConn(true);
    ws.send(JSON.stringify({ type: "start", sample_rate: SAMPLE_RATE }));
  };
  ws.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    if (msg.type === "transcript") handleTranscript(msg);
    else if (msg.type === "error") setStatus(`Transcription error: ${msg.detail || "unknown"}`);
  };
  ws.onclose = () => setConn(false);
  ws.onerror = () => setStatus("Could not reach the transcription server (is the backend running?).");
}

function handleTranscript({ text, is_final }) {
  if (!text) return;
  if (is_final) {
    finalText = joinText(finalText, text);
    interimText = "";
    persist();
  } else {
    interimText = text;
  }
  render();
}

// ---------------------------------------------------------------------------
// Audio capture → 16kHz Int16 PCM
// ---------------------------------------------------------------------------
async function startAudioGraph() {
  audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });
  await audioContext.audioWorklet.addModule(chrome.runtime.getURL("sidepanel/pcm-processor.js"));

  sourceNode = audioContext.createMediaStreamSource(mediaStream);
  workletNode = new AudioWorkletNode(audioContext, "pcm-processor");
  workletNode.port.onmessage = (e) => {
    pending.push(e.data);
    updateMeter(e.data);
  };

  sourceNode.connect(workletNode);
  // Worklet writes no output, so connecting to destination stays silent (no echo).
  workletNode.connect(audioContext.destination);

  flushTimer = setInterval(flush, FLUSH_MS);
}

function stopAudioGraph() {
  clearInterval(flushTimer);
  flushTimer = null;
  flush(); // send whatever is buffered
  pending = [];

  if (sourceNode) sourceNode.disconnect();
  if (workletNode) workletNode.disconnect();
  if (audioContext) audioContext.close();
  if (mediaStream) mediaStream.getTracks().forEach((t) => t.stop());
  sourceNode = workletNode = audioContext = mediaStream = null;
  setMeter(0);
}

// Concatenate pending Float32 frames, resample to 16kHz if needed, convert to
// Int16 little-endian, and ship the bytes.
function flush() {
  if (!pending.length || !ws || ws.readyState !== WebSocket.OPEN) {
    pending = [];
    return;
  }
  const total = pending.reduce((n, c) => n + c.length, 0);
  const merged = new Float32Array(total);
  let offset = 0;
  for (const chunk of pending) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  pending = [];

  const rate = audioContext ? audioContext.sampleRate : SAMPLE_RATE;
  const resampled = rate === SAMPLE_RATE ? merged : downsample(merged, rate, SAMPLE_RATE);
  ws.send(floatToPCM16(resampled));
}

function downsample(input, inRate, outRate) {
  const ratio = inRate / outRate;
  const outLen = Math.floor(input.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const pos = i * ratio;
    const idx = Math.floor(pos);
    const frac = pos - idx;
    out[i] = input[idx] * (1 - frac) + (input[idx + 1] || input[idx]) * frac;
  }
  return out;
}

function floatToPCM16(float32) {
  const buffer = new ArrayBuffer(float32.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

// ---------------------------------------------------------------------------
// UI helpers
// ---------------------------------------------------------------------------
function render() {
  if (!finalText && !interimText) {
    els.transcript.innerHTML = '<span class="placeholder">Your live transcript will show up here…</span>';
    return;
  }
  els.transcript.innerHTML =
    `<span class="final">${escapeHtml(finalText)}</span>` +
    (interimText ? ` <span class="interim">${escapeHtml(interimText)}</span>` : "");
  els.transcript.scrollTop = els.transcript.scrollHeight;
}

function persist() {
  chrome.storage.session.set({ [STORAGE_KEY]: finalText });
}

function joinText(a, b) {
  return a ? `${a} ${b}`.replace(/\s+/g, " ").trim() : b.trim();
}

function setStatus(text) {
  els.status.textContent = text;
}

function setConn(live) {
  els.conn.classList.toggle("live", live);
  els.conn.title = live ? "Connected" : "Disconnected";
}

function updateMeter(frame) {
  let sum = 0;
  for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
  const rms = Math.sqrt(sum / frame.length);
  setMeter(Math.min(100, rms * 300));
}

function setMeter(pct) {
  const bar = els.meter.querySelector("i");
  if (bar) bar.style.width = `${pct}%`;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
