import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Domain } from "../api";

export default function Dashboard() {
  const [me, setMe] = useState<any>(null);
  const [sessions, setSessions] = useState<any[]>([]);
  const [title, setTitle] = useState("");
  const [slidesUrl, setSlidesUrl] = useState("");

  async function load() {
    setMe(await api.me());
    setSessions(await api.sessions());
  }
  useEffect(() => { load(); }, []);

  async function start(e: React.FormEvent) {
    e.preventDefault();
    await api.createSession({ domain: me.domain as Domain, title, slides_url: slidesUrl });
    setTitle("");
    setSlidesUrl("");
    load();
  }

  return (
    <div>
      {me && (
        <header className="hero">
          <h2>Welcome back, {me.display_name}</h2>
          <p>Domain: <b>{me.domain}</b> · Improvement score: <b>{me.improvement_score}</b></p>
        </header>
      )}

      <section className="card">
        <h3>Start a practice run</h3>
        <p className="muted">Open your Google Slides, launch the Heard extension, then start speaking. Or create a run here first.</p>
        <form className="row" onSubmit={start}>
          <input placeholder="Practice title (e.g. Series A pitch)" value={title} onChange={(e) => setTitle(e.target.value)} required />
          <input placeholder="Google Slides URL (optional)" value={slidesUrl} onChange={(e) => setSlidesUrl(e.target.value)} />
          <button type="submit">Create run</button>
        </form>
      </section>

      <section>
        <h3>Your practices</h3>
        {sessions.length === 0 && <p className="muted">No runs yet — create one above.</p>}
        <ul className="list">
          {sessions.map((s) => (
            <li key={s.id}>
              <Link to={`/session/${s.id}`}>
                <span>{s.title}</span>
                <span className="badge">{s.score != null ? `${s.score}/100` : "not scored"}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
