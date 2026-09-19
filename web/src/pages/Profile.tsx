import { useEffect, useState } from "react";
import { api, currentUserId } from "../api";

// The user's own profile: averaged metrics across their top speeches + history.
export default function Profile() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const uid = await currentUserId();
        if (!uid) return;
        setData(await api.profile(uid));
      } catch (err) {
        setError(String(err));
      }
    })();
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading profile…</p>;

  const m = data.average_metrics ?? {};
  const keys = ["clarity", "volume", "pace", "confidence", "structure", "overall"];

  return (
    <div>
      <h2>{data.user?.name || "Your profile"}</h2>
      {data.user?.career_tag && <span className="badge">{data.user.career_tag}</span>}
      {data.user?.is_mentor && <span className="badge">Mentor</span>}

      <div className="card">
        <h3>Average metrics</h3>
        <div className="bars">
          {keys.map((k) => (
            <div key={k} className="bar-row">
              <span className="bar-label">{k}</span>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${m[k] ?? 0}%` }} />
              </div>
              <span className="bar-val">{Math.round(m[k] ?? 0)}</span>
            </div>
          ))}
        </div>
      </div>

      <h3>Top speeches</h3>
      {(data.top_speeches ?? []).length === 0 && <p className="muted">No speeches yet.</p>}
      <ul className="list">
        {(data.top_speeches ?? []).map((s: any) => (
          <li key={s.id}>
            <span>{new Date(s.started_at).toLocaleString()}</span>
            <a href={`/session/${s.id}`}>Open</a>
          </li>
        ))}
      </ul>
    </div>
  );
}
