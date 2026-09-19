import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken, type Domain } from "../api";

export default function Login() {
  const nav = useNavigate();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [domain, setDomain] = useState<Domain>("tech");
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const res =
        mode === "login"
          ? await api.login(email, password)
          : await api.signup({ email, password, display_name: displayName, domain });
      setToken(res.access_token);
      nav("/");
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <div className="auth-card">
      <h1>Heard</h1>
      <p className="tagline">Practice your pitch. Get heard.</p>
      <form onSubmit={submit}>
        {mode === "signup" && (
          <input placeholder="Display name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
        )}
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        {mode === "signup" && (
          <select value={domain} onChange={(e) => setDomain(e.target.value as Domain)}>
            <option value="tech">Tech</option>
            <option value="law">Law</option>
            <option value="finance">Finance</option>
            <option value="marketing">Marketing</option>
          </select>
        )}
        <button type="submit">{mode === "login" ? "Log in" : "Create account"}</button>
      </form>
      {error && <p className="error">{error}</p>}
      <button className="link" onClick={() => setMode(mode === "login" ? "signup" : "login")}>
        {mode === "login" ? "Need an account? Sign up" : "Already have an account? Log in"}
      </button>
    </div>
  );
}
