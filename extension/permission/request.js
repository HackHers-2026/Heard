// A normal extension tab whose only job is to trigger the microphone permission
// prompt. Extension side panels/popups often can't show the mic prompt
// themselves, but a top-level extension page can — and the grant is remembered
// for the whole extension origin, so the side panel can use the mic afterwards.
const statusEl = document.getElementById("status");
const hintEl = document.getElementById("hint");
const retryBtn = document.getElementById("retry");

async function requestMic() {
  statusEl.className = "status";
  statusEl.textContent = "Requesting access…";
  hintEl.textContent = "";
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    // We only needed the grant — release the device immediately.
    stream.getTracks().forEach((t) => t.stop());

    statusEl.className = "status ok";
    statusEl.textContent = "Microphone allowed! Returning to Heard…";
    await chrome.storage.session.set({ heard_mic_granted: true });
    chrome.runtime.sendMessage({ type: "MIC_PERMISSION", granted: true });
    setTimeout(() => window.close(), 900);
  } catch (err) {
    statusEl.className = "status err";
    statusEl.textContent = `Microphone ${err.name === "NotAllowedError" ? "blocked" : "error"}: ${err.name}`;
    hintEl.innerHTML =
      "If you previously blocked it, click the <b>tune/lock icon</b> to the left of this page's address, " +
      "set <b>Microphone</b> to <b>Allow</b>, then click “Allow microphone” again.";
    chrome.runtime.sendMessage({ type: "MIC_PERMISSION", granted: false, error: err.name });
  }
}

retryBtn.addEventListener("click", requestMic);
requestMic();
