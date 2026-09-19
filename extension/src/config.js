// Shared config for the extension. Point these at your deployed backend later.
export const API_BASE = "http://localhost:8000";

// WebSocket the side panel streams mic audio to. The backend proxies it to
// ElevenLabs Scribe realtime v2 and streams transcripts back.
export const STT_WS_URL = "ws://localhost:8000/ws/stt";

// Sample rate we capture + send. ElevenLabs realtime STT expects 16kHz mono PCM.
export const SAMPLE_RATE = 16000;
