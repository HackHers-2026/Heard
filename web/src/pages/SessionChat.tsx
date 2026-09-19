import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, Phase } from "../api";

// The AI coach chat for a speech session + the final report (metrics + summary).
// The Chrome extension streams live nudges into the same speech; here the user
// can talk to the coach (preptalk/talksummary) and generate the post-speech report.
export default function SessionChat() {
  const { id } = useParams();
  const speechId = id as string;

  const [phase, setPhase] = useState<Phase>("preptalk");
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [report, setReport] = useState<any>(null);
  const [finishing, setFinishing] = useState(false);
  const [error, setError] = useState("");
  const [mentorStatus, setMentorStatus] = useState("");
  const pollRef = useRef<number | null>(null);

  async function loadThread() {
    try {
      const res = await api.getChat(speechId);
      setMessages(res.messages ?? []);
    } catch (err) {
      setError(String(err));
    }
  }
  useEffect(() => {
    loadThread();
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [speechId]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;
    setSending(true);
    setError("");
    try {
      await api.postChat(speechId, input.trim(), phase);
      setInput("");
      await loadThread();
    } catch (err) {
      setError(String(err));
    } finally {
      setSending(false);
    }
  }

  async function finish() {
    setFinishing(true);
    setError("");
    try {
      const { report_ready } = await api.endSpeech(speechId);
      setPhase("talksummary");
      if (report_ready) {
        setReport(await api.report(speechId));
      } else {
        // report is generated async — poll a few times
        pollRef.current = window.setInterval(async () => {
          try {
            const r = await api.report(speechId);
            if (r?.metrics) {
              setReport(r);
              if (pollRef.current) window.clearInterval(pollRef.current);
            }
          } catch {
            /* keep polling */
          }
        }, 3000);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setFinishing(false);
    }
  }

  async function connectMentor(mentorId: string) {
    setMentorStatus("");
    try {
      const res = await api.mentorConnect(mentorId, speechId);
      setMentorStatus(`Request sent (${res.connection?.status ?? "pending"})`);
    } catch (err) {
      setMentorStatus(String(err));
    }
  }

  return (
    <div>
      <h2>Practice session</h2>
      <p className="muted">Speech ID: {speechId}</p>

      <div className="tabs">
        {(["preptalk", "activetalk", "talksummary"] as Phase[]).map((p) => (
          <button key={p} className={phase === p ? "active" : ""} onClick={() => setPhase(p)}>
            {p}
          </button>
        ))}
      </div>

      <div className="chat">
        {messages.length === 0 && (
          <p className="muted">No messages yet. Talk to your coach below, or start recording in the extension.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role === "model" ? "summary" : ""}`}>
            <p>{m.content}</p>
            {m.summary && <span className="badge">{m.summary}</span>}
          </div>
        ))}
      </div>

      <form onSubmit={send} className="row">
        <input
          placeholder={`Message the coach (${phase})…`}
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit" disabled={sending}>
          {sending ? "…" : "Send"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      <button onClick={finish} disabled={finishing} style={{ marginTop: 16 }}>
        {finishing ? "Generating…" : "Finish & get my report"}
      </button>

      {report?.metrics && (
        <div className="card summary">
          <h3>Report — {report.metrics.overall}/100</h3>
          <p>{report.metrics.summary}</p>
          <MetricBars metrics={report.metrics} />
          {report.metrics.suggestions?.length > 0 && (
            <>
              <h4>Work on</h4>
              <ul>
                {report.metrics.suggestions.map((s: string, i: number) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </>
          )}
          {report.metrics.mentor_suggestions?.length > 0 && (
            <>
              <h4>Connect with a mentor</h4>
              <div className="row">
                {report.metrics.mentor_suggestions.map((mid: string) => (
                  <button key={mid} className="ghost" onClick={() => connectMentor(mid)}>
                    Request {mid.slice(0, 8)}…
                  </button>
                ))}
              </div>
              {mentorStatus && <p className="muted">{mentorStatus}</p>}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function MetricBars({ metrics }: { metrics: any }) {
  const keys = ["clarity", "volume", "pace", "confidence", "structure"];
  return (
    <div className="bars">
      {keys.map((k) => (
        <div key={k} className="bar-row">
          <span className="bar-label">{k}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${metrics[k] ?? 0}%` }} />
          </div>
          <span className="bar-val">{metrics[k] ?? 0}</span>
        </div>
      ))}
    </div>
  );
}
