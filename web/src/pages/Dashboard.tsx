import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, currentUserId } from "../api";

// Flow 1 (pre-speech encouragement) entry + starting a new speech session,
// plus a list of the user's recent speeches (from their profile).
export default function Dashboard() {
  const nav = useNavigate();
  const [encouragement, setEncouragement] = useState("");
  const [speeches, setSpeeches] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function loadRecent() {
    try {
      const uid = await currentUserId();
      if (!uid) return;
      const profile = await api.profile(uid);
      setSpeeches(profile.top_speeches ?? []);
    } catch (err) {
      setError(String(err));
    }
  }
  useEffect(() => {
    loadRecent();
  }, []);

  async function encourageMe() {
    setBusy(true);
    setError("");
    try {
      const res = await api.encourage("quick");
      setEncouragement(res.message);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function startSpeech() {
    setBusy(true);
    setError("");
    try {
      const { speech_id } = await api.startSpeech();
      nav(`/session/${speech_id}`);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <header className="hero">
        <h2>Ready to be heard?</h2>
        <p className="muted">Get a confidence boost, then start practicing your pitch.</p>
      </header>

      <section className="card">
        <div className="row">
          <button onClick={encourageMe} disabled={busy} className="ghost">
            {busy ? "…" : "Encourage me"}
          </button>
          <button onClick={startSpeech} disabled={busy}>
            Start a practice speech
          </button>
        </div>
        {encouragement && <p style={{ marginTop: 12 }}>{encouragement}</p>}
      </section>

      {error && <p className="error">{error}</p>}

      <section>
        <h3>Your recent speeches</h3>
        {speeches.length === 0 && <p className="muted">No speeches yet — start one above.</p>}
        <ul className="list">
          {speeches.map((s) => (
            <li key={s.id}>
              <span>{new Date(s.started_at).toLocaleString()}</span>
              <a href={`/session/${s.id}`}>Open</a>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
