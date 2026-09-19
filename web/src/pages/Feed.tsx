import { useEffect, useState } from "react";
import { api, CareerTag } from "../api";

const TAGS: CareerTag[] = ["engineering", "finance", "marketing", "law"];

// Community feed: public speeches by domain, with like toggling.
export default function Feed() {
  const [careerTag, setCareerTag] = useState<string>("");
  const [posts, setPosts] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const res = await api.feed(careerTag || undefined);
      setPosts(res.posts ?? []);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, [careerTag]);

  async function toggleLike(postId: string) {
    try {
      const { like_count } = await api.like(postId);
      setPosts((prev) => prev.map((p) => (p.id === postId ? { ...p, like_count } : p)));
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <div>
      <h2>Community feed</h2>
      <p className="muted">See how other women are refining their pitches — filter by domain.</p>

      <div className="tabs">
        <button className={careerTag === "" ? "active" : ""} onClick={() => setCareerTag("")}>
          all
        </button>
        {TAGS.map((t) => (
          <button key={t} className={careerTag === t ? "active" : ""} onClick={() => setCareerTag(t)}>
            {t}
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}
      {loading && <p className="muted">Loading…</p>}

      <ul className="list">
        {!loading && posts.length === 0 && <p className="muted">No posts yet in this domain.</p>}
        {posts.map((p) => (
          <li key={p.id}>
            <span>
              {p.topic_tag || "Untitled"} <span className="badge">{p.career_tag}</span>
            </span>
            <button className="link" onClick={() => toggleLike(p.id)}>
              ♥ {p.like_count ?? 0}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
