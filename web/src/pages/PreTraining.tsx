import { useState } from "react";
import { api } from "../api";

// Flow 1 (pre-speech): "Encourage me" in quick or plan mode. Plan mode also
// returns a suggested outline for what the user is about to present.
export default function PreTraining() {
  const [mode, setMode] = useState<"quick" | "plan">("plan");
  const [context, setContext] = useState("");
  const [message, setMessage] = useState("");
  const [outline, setOutline] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api.encourage(mode, context || undefined);
      setMessage(res.message);
      setOutline(res.outline ?? []);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h2>Pre-training</h2>
      <p className="muted">Prep your mindset and structure before you present.</p>

      <div className="tabs">
        <button className={mode === "quick" ? "active" : ""} onClick={() => setMode("quick")}>
          Quick boost
        </button>
        <button className={mode === "plan" ? "active" : ""} onClick={() => setMode("plan")}>
          Plan my talk
        </button>
      </div>

      <form onSubmit={submit} className="card">
        <textarea
          placeholder={
            mode === "plan"
              ? "What are you presenting? (topic, audience, goal)"
              : "Optional: what's on your mind?"
          }
          value={context}
          onChange={(e) => setContext(e.target.value)}
          rows={3}
          style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid var(--border)" }}
        />
        <button type="submit" disabled={busy} style={{ marginTop: 10 }}>
          {busy ? "Thinking…" : "Coach me"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {message && (
        <div className="card">
          <p>{message}</p>
          {outline.length > 0 && (
            <>
              <h4>Suggested outline</h4>
              <ol>
                {outline.map((o, i) => (
                  <li key={i}>{o}</li>
                ))}
              </ol>
            </>
          )}
        </div>
      )}
    </div>
  );
}
