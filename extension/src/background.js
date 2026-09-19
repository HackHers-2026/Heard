// Service worker: owns auth token + all network calls so content scripts stay thin.
import { API_BASE } from "./config.js";

async function getToken() {
  const { heard_token } = await chrome.storage.local.get("heard_token");
  return heard_token || null;
}

async function authedFetch(path, options = {}) {
  const token = await getToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// Message router for popup + content script.
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      switch (msg.type) {
        case "LOGIN": {
          const body = new URLSearchParams({ username: msg.email, password: msg.password });
          const res = await fetch(`${API_BASE}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body,
          });
          if (!res.ok) throw new Error("Login failed");
          const data = await res.json();
          await chrome.storage.local.set({ heard_token: data.access_token });
          sendResponse({ ok: true });
          break;
        }
        case "CREATE_SESSION": {
          const run = await authedFetch("/sessions", {
            method: "POST",
            body: JSON.stringify({ domain: msg.domain, title: msg.title, slides_url: msg.slidesUrl }),
          });
          await chrome.storage.local.set({ heard_active_session: run.id });
          sendResponse({ ok: true, session: run });
          break;
        }
        case "LIVE_FEEDBACK": {
          const fb = await authedFetch("/feedback/live", {
            method: "POST",
            body: JSON.stringify({ session_id: msg.sessionId, text: msg.text }),
          });
          sendResponse({ ok: true, feedback: fb });
          break;
        }
        case "SUMMARIZE": {
          const summary = await authedFetch(`/feedback/summarize?session_id=${msg.sessionId}`, {
            method: "POST",
          });
          sendResponse({ ok: true, summary });
          break;
        }
        default:
          sendResponse({ ok: false, error: "unknown message" });
      }
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();
  return true; // keep the message channel open for the async response
});
