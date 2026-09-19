# Task 09 — Chrome Extension (Manifest V3)

**Status:** todo  
**Owner:** extension/  
**Reads:** docs/contracts.md

---

## Goal

Dual-stream audio capture: Web Speech API for transcript + Web Audio API for volume. Push segments to backend every 2 min. Display nudge in overlay.

---

## Architecture

```
content.js        — injected into active tab; thin message relay only
background.js     — service worker; owns auth token; makes all backend calls
popup/            — start/stop session UI; shows live nudge
overlay.css       — floating nudge card styles
```

Content scripts NEVER call the backend directly — they send `chrome.runtime.sendMessage` to the service worker (single token owner).

---

## Streams (run in parallel)

### Web Speech API (transcript)
```js
const recognition = new webkitSpeechRecognition()
recognition.continuous = true
recognition.interimResults = false
// collect results until 2-min timer fires → flush segment
```

### Web Audio API (volume)
```js
const ctx = new AudioContext()
const analyser = ctx.createAnalyser()
// sample amplitude every 100ms → running avg → send as avg_volume (0-100)
```

---

## Segment flush (every 2 min)
```
POST /api/speech/segment  {
  speech_id, transcript, segment_index,
  recorded_at, duration_seconds: 120,
  avg_volume, volume_variance
}
→ response.nudge → show in overlay
```

---

## Session lifecycle

| Action | Sends |
|--------|-------|
| Click Start | POST /api/speech/start → store speech_id + session_token |
| Every 2 min | POST /api/speech/segment → update overlay with nudge |
| Click Stop | POST /api/speech/end → open web app report page |

---

## Permissions (manifest.json)
```json
"permissions": ["activeTab", "storage"],
"host_permissions": ["http://localhost:8000/*", "https://*.heard.app/*"]
```

---

## Token storage
Store Supabase JWT in `chrome.storage.session` (not local — cleared on browser close). Popup reads it for the Authorization header passed to service worker.
