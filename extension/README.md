# Heard — Chrome Extension (Manifest V3)

The live-coaching frontend. Runs on top of Google Slides: it captures your
speech while you practice, sends transcript chunks to the backend, and shows
Gemini's encouraging tips as pop-ups in an overlay.

## Load it

1. Start the backend (`http://localhost:8000`).
2. Go to `chrome://extensions`, enable **Developer mode**.
3. **Load unpacked** → select this `extension/` folder.
4. Copy the extension ID and add `chrome-extension://<ID>` to the backend's
   `CORS_ORIGINS` in `.env`.

## Use it

1. Click the Heard toolbar icon → log in → **Start practice run** (pick a domain).
2. Open your Google Slides deck.
3. Hit **Start** on the overlay (top-right) and begin your pitch.
4. Tips pop up live. Hit **Stop** to finish — your score + full report appear in the web app.

## Files
- `manifest.json` — MV3 config, permissions, content-script matcher
- `src/background.js` — service worker; owns the JWT + all API calls
- `src/content.js` — overlay + speech capture on Google Slides
- `src/overlay.css` — overlay styling
- `popup/` — login + start-a-run UI

## Notes
- Uses the browser Web Speech API for fast client-side transcription in the demo.
  For production ElevenLabs transcription, capture `getUserMedia` audio and POST
  chunks to `/feedback/transcribe` instead.
