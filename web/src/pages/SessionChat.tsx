import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";

// The transcript + AI feedback rendered as a chat with the coach, plus a
// button to generate the final summary + score.
export default function SessionChat() {
  const { id } = useParams();
  const sessionId = Number(id);
  const [feedback, setFeedback] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setFeedback(await api.sessionFeedback(sessionId));
  }
  useEffect(() => { load(); }, [sessionId]);

  async function finish() {
    setLoading(true);
    try {
      setSummary(await api.summarize(sessionId));
      await load();
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h2>Practice #{sessionId}</h2>
      <div className="chat">
        {feedback.length === 0 && <p className="muted">No feedback captured yet. Practice with the extension to populate this chat.</p>}
        {feedback.map((f) => (
          <div key={f.id} className={`bubble ${f.kind}`}>
            {f.trigger_text && <p className="trigger">You said: “{f.trigger_text}”</p>}
            <p>{f.content}</p>
            {f.score != null && <span className="badge">Score: {f.score}/100</span>}
          </div>
        ))}
      </div>

      <button onClick={finish} disabled={loading}>
        {loading ? "Scoring…" : "Finish & get my score"}
      </button>

      {summary && (
        <div className="card summary">
          <h3>Summary — {summary.score}/100</h3>
          <p>{summary.summary}</p>
          <div className="cols">
            <div>
              <h4>Strengths</h4>
              <ul>{summary.strengths.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>
            </div>
            <div>
              <h4>Work on</h4>
              <ul>{summary.improvements.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
