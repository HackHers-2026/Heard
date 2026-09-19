# Heard — Chrome Extension (Manifest V3, Side Panel)

A **sidebar** (Chrome Side Panel) that opens on any tab. It asks for microphone
access, records while you practice, and shows a **live transcript** powered by
ElevenLabs Scribe realtime v2.

## Load it

1. Start the backend (`http://localhost:8000`) — see `../backend/README.md`.
2. Go to `chrome://extensions`, enable **Developer mode**.
3. **Load unpacked** → select this `extension/` folder.
4. Click the **Heard** toolbar icon on any tab → the side panel opens.

## Use it

1. Click **Start recording**. The **first time**, a small tab opens asking for
   microphone access — click **Allow**. (Side panels can't show the mic prompt
   directly, so Heard requests it from a normal extension tab; the grant is
   remembered for the whole extension, so you only do this once.)
2. Speak. Words stream into the transcript live (interim text is grey, finalized
   text is solid).
3. Click **Stop** to end. **Clear** wipes the current transcript.

> If you had previously **blocked** the mic: in the permission tab, click the
> tune/lock icon left of the address bar, set **Microphone → Allow**, then retry.

## Where the transcript lives (this step)

- **In the side panel** while recording — kept in memory (`finalText` /
  `interimText`) and rendered live.
- **`chrome.storage.session`** — mirrored so it survives closing/reopening the
  panel or switching tabs during the browser session.
- It is **not** written to the backend database yet — persisting a finished
  transcript to the DB comes in a later step.

## How audio flows

```
mic → getUserMedia → AudioWorklet (pcm-processor.js) → 16kHz Int16 PCM
    → WebSocket ws://localhost:8000/ws/stt
    → backend proxy → ElevenLabs Scribe realtime v2
    → {type:"transcript", text, is_final} frames → rendered in the panel
```

The **API key stays on the backend** — the extension never sees it. Without a
key, the backend streams a stub transcript so you can test the full pipeline.

## Sign-in / who owns a recording

You don't sign in *inside* the extension. Instead:

1. Sign in on the **web app** (`http://localhost:5173`) with Supabase.
2. A content script (`src/webapp-bridge.js`) injected on the web app origin
   reads the Supabase session from `localStorage` and mirrors the access token
   into the extension (`chrome.storage.local.heard_token`).
3. When you record, the side panel sends that token to `/ws/stt` (as a
   `?token=` query param — browsers can't set WebSocket headers), so the backend
   attributes the `Speech` + segments to your real account.

No token yet? Recordings are stored under a stand-in demo user — nothing breaks.

**Deploying:** add your production web-app origin to the `content_scripts.matches`
in `manifest.json` (e.g. `https://your-app.vercel.app/*`) so the bridge runs there too.
Also requires `SUPABASE_JWT_SECRET` set on the backend.

## Files
- `manifest.json` — MV3 config, `side_panel`, permissions, web-app content script
- `src/background.js` — opens the side panel on icon click; REST helpers for later steps
- `src/config.js` — backend URLs + sample rate
- `src/webapp-bridge.js` — content script that syncs the Supabase token from the web app
- `sidepanel/sidepanel.html|css|js` — the sidebar UI + recording logic
- `sidepanel/pcm-processor.js` — AudioWorklet that captures raw PCM frames
