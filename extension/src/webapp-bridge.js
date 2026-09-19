// Content script injected into the Heard WEB APP origin.
//
// Its only job: read the Supabase session the web app stores in localStorage
// and mirror the access token into the extension's chrome.storage.local as
// `heard_token`. The side panel then sends that token to /ws/stt so recordings
// are attributed to the signed-in user (instead of the demo user).
//
// The user just signs in on the web app once — no separate extension login.

// Supabase JS (v2) persists the session under a key like `sb-<ref>-auth-token`.
function readSupabaseToken() {
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith("sb-") && key.endsWith("-auth-token")) {
        const parsed = JSON.parse(localStorage.getItem(key));
        // v2 stores the session object directly; older shapes nest it.
        return (
          parsed?.access_token ||
          parsed?.currentSession?.access_token ||
          parsed?.[0] || // some builds store [access_token, refresh_token]
          null
        );
      }
    }
  } catch (err) {
    console.warn("[Heard bridge] could not read Supabase session:", err);
  }
  return null;
}

async function sync() {
  const token = readSupabaseToken();
  const { heard_token } = await chrome.storage.local.get("heard_token");

  if (token && token !== heard_token) {
    await chrome.storage.local.set({ heard_token: token });
    console.info("[Heard bridge] synced auth token to the extension.");
  } else if (!token && heard_token) {
    // User signed out on the web app — clear the extension token too.
    await chrome.storage.local.remove("heard_token");
    console.info("[Heard bridge] cleared auth token (signed out).");
  }
}

// Run now, on cross-tab storage changes, and on an interval to catch same-tab
// token refreshes/expiry rotations that don't fire a `storage` event.
sync();
window.addEventListener("storage", sync);
setInterval(sync, 5000);
