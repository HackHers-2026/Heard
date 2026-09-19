// Service worker.
// 1) Makes the Heard side panel open on ANY tab when the toolbar icon is clicked.
// 2) Owns auth token + REST calls used by later steps (login, sessions, feedback).
//    The live speech-to-text stream is handled directly in the side panel over a
//    WebSocket — see sidepanel/sidepanel.js.
import { API_BASE } from "./config.js";

// Open the side panel on the current tab when the user clicks the toolbar icon.
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((err) => console.error("sidePanel behavior:", err));
});

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

// Message router used by the side panel for REST calls (auth/sessions/feedback).
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
        default:
          sendResponse({ ok: false, error: "unknown message" });
      }
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();
  return true; // keep the message channel open for the async response
});
