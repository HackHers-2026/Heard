import { useEffect, useState } from "react";
import { api } from "../api";

// Minimal DM view: pick a user id (e.g. from ?to= on the leaderboard) and chat.
export default function Messages() {
  const params = new URLSearchParams(location.search);
  const initialTo = params.get("to") ? Number(params.get("to")) : 0;
  const [otherId, setOtherId] = useState(initialTo);
  const [thread, setThread] = useState<any[]>([]);
  const [body, setBody] = useState("");

  async function load() {
    if (otherId) setThread(await api.thread(otherId));
  }
  useEffect(() => { load(); }, [otherId]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!otherId || !body) return;
    await api.sendMessage(otherId, body);
    setBody("");
    load();
  }

  return (
    <div>
      <h2>Messages</h2>
      <div className="row">
        <input
          type="number"
          placeholder="Mentor user id"
          value={otherId || ""}
          onChange={(e) => setOtherId(Number(e.target.value))}
        />
      </div>

      <div className="chat">
        {thread.map((m) => (
          <div key={m.id} className="bubble">
            <p className="trigger">from #{m.sender_id}</p>
            <p>{m.body}</p>
          </div>
        ))}
      </div>

      <form className="row" onSubmit={send}>
        <input placeholder="Ask for advice…" value={body} onChange={(e) => setBody(e.target.value)} />
        <button type="submit">Send</button>
      </form>
    </div>
  );
}
