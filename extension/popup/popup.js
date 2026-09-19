// Popup: log in and start a practice run. All network calls go through the
// service worker so the token lives in one place.
const $ = (id) => document.getElementById(id);
const status = $("status");

function send(type, payload) {
  return new Promise((resolve) => chrome.runtime.sendMessage({ type, ...payload }, resolve));
}

async function refreshView() {
  const { heard_token } = await chrome.storage.local.get("heard_token");
  $("login-view").classList.toggle("hidden", !!heard_token);
  $("session-view").classList.toggle("hidden", !heard_token);
}

$("login-btn").addEventListener("click", async () => {
  status.textContent = "Logging in…";
  const res = await send("LOGIN", { email: $("email").value, password: $("password").value });
  status.textContent = res.ok ? "Logged in!" : `Error: ${res.error}`;
  if (res.ok) refreshView();
});

$("start-btn").addEventListener("click", async () => {
  status.textContent = "Creating run…";
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const slidesUrl = tab?.url?.includes("docs.google.com/presentation") ? tab.url : null;
  const res = await send("CREATE_SESSION", {
    title: $("title").value || "Untitled practice",
    domain: $("domain").value,
    slidesUrl,
  });
  status.textContent = res.ok
    ? `Run #${res.session.id} started — go to your slides and press Start.`
    : `Error: ${res.error}`;
});

refreshView();
