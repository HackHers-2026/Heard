import { useState } from "react";
import { api, type Domain } from "../api";

const DOMAINS: Domain[] = ["tech", "law", "finance", "marketing"];

export default function PreTraining() {
  const [domain, setDomain] = useState<Domain>("tech");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  async function coachMe() {
    setLoading(true);
    try {
      setData(await api.preTraining(domain));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h2>Pre-training</h2>
      <p className="muted">Get domain-specific coaching before you start practicing.</p>
      <div className="tabs">
        {DOMAINS.map((d) => (
          <button key={d} className={d === domain ? "active" : ""} onClick={() => setDomain(d)}>{d}</button>
        ))}
      </div>
      <button onClick={coachMe} disabled={loading}>{loading ? "Thinking…" : "Coach me"}</button>

      {data && (
        <div className="card">
          <p>{data.coaching}</p>
          <h4>Checklist</h4>
          <ul>{data.checklist.map((c: string, i: number) => <li key={i}>{c}</li>)}</ul>
        </div>
      )}
    </div>
  );
}
