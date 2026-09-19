import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { setToken } from "../api";
import { supabase } from "../supabase";

type AuthMode = "login" | "signup";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const returnTo =
    (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? "/pre-training";

  useEffect(() => {
    supabase.auth.getSession()
      .then(({ data }) => {
        if (data.session?.access_token) navigate(returnTo, { replace: true });
      })
      .catch(() => undefined);
  }, [navigate, returnTo]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      if (mode === "login") {
        const { data, error: authError } = await supabase.auth.signInWithPassword({ email, password });
        if (authError) throw authError;
        if (!data.session) throw new Error("Sign in completed without an active session.");
        setToken(data.session.access_token);
        navigate(returnTo, { replace: true });
      } else {
        const { data, error: authError } = await supabase.auth.signUp({
          email,
          password,
          options: { data: { display_name: displayName.trim() || undefined } },
        });
        if (authError) throw authError;

        // With email confirmation disabled in Supabase, signUp returns a session
        // immediately. If it doesn't, sign in with the same credentials so the
        // user still lands in the app without any verification step.
        let session = data.session;
        if (!session) {
          const { data: signInData, error: signInError } =
            await supabase.auth.signInWithPassword({ email, password });
          if (signInError) throw signInError;
          session = signInData.session;
        }
        if (!session) throw new Error("Account created, but sign in failed. Please sign in.");
        setToken(session.access_token);
        navigate("/pre-training", { replace: true });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  function switchMode() {
    setMode((current) => (current === "login" ? "signup" : "login"));
    setError("");
  }

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="auth-title">
        <div className="auth-brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="wordmark">HEARD</span>
        </div>

        <div className="auth-heading">
          <p className="eyebrow">Communication workspace</p>
          <h1 id="auth-title">{mode === "login" ? "Sign in" : "Create your account"}</h1>
          <p>
            {mode === "login"
              ? "Continue your preparation, coaching, and conversations."
              : "Build a private record of your speaking progress."}
          </p>
        </div>

        <form className="auth-form" onSubmit={submit}>
          {mode === "signup" && (
            <label>
              <span>Display name</span>
              <input
                autoComplete="name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                required
              />
            </label>
          )}
          <label>
            <span>Email</span>
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label>
            <span>Password</span>
            <input
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={6}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>

          {error && <p className="form-message is-error" role="alert">{error}</p>}

          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting ? "Please wait…" : mode === "login" ? "Continue" : "Create account"}
          </button>
        </form>

        <p className="auth-switch">
          {mode === "login" ? "New to Heard?" : "Already have an account?"}{" "}
          <button type="button" onClick={switchMode}>
            {mode === "login" ? "Create an account" : "Sign in"}
          </button>
        </p>
      </section>
    </main>
  );
}
