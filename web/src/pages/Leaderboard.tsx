import { useEffect, useState } from "react";
import { api, type Domain } from "../api";

const DOMAINS: Domain[] = ["tech", "law", "finance", "marketing"];

export default function Leaderboard() {
  const [domain, setDomain] = useState<Domain>("tech");
  const [rows, setRows] = useState<any[]>([]);
  const [mentors, setMentors] = useState<any[]>([]);

  useEffect(() => {
    api.leaderboard(domain).then(setRows).catch(() => setRows([]));
    api.mentors(domain).then(setMentors).catch(() => setMentors([]));
  }, [domain]);

  return (
    <div>
      <h2>Leaderboard</h2>
      <div className="tabs">
        {DOMAINS.map((d) => (
          <button key={d} className={d === domain ? "active" : ""} onClick={() => setDomain(d)}>
            {d}
          </button>
        ))}
      </div>

      <ol className="leaderboard">
        {rows.map((r) => (
          <li key={r.user_id}>
            <span className="rank">#{r.rank}</span>
            <span>{r.display_name}{r.is_mentor && <span className="badge">mentor</span>}</span>
            <span className="score">{r.improvement_score}</span>
          </li>
        ))}
      </ol>

      <section className="card">
        <h3>Recommended mentors in {domain}</h3>
        {mentors.length === 0 && <p className="muted">No mentors yet.</p>}
        <ul className="list">
          {mentors.map((m) => (
            <li key={m.id}>
              <span>{m.display_name} · score {m.improvement_score}</span>
              <a href={`/messages?to=${m.id}`}>DM</a>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
