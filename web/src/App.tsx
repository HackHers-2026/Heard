import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { clearToken, getToken, setToken } from "./api";
import HeardWorkspace from "./components/HeardWorkspace";
import Login from "./pages/Login";
import { supabase } from "./supabase";

function useSessionState() {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(Boolean(getToken()));

  useEffect(() => {
    let active = true;
    supabase.auth.getSession()
      .then(({ data }) => {
        if (!active) return;
        if (data.session?.access_token) setToken(data.session.access_token);
        setAuthenticated(Boolean(data.session?.access_token ?? getToken()));
        setReady(true);
      })
      .catch(() => {
        if (!active) return;
        clearToken();
        setAuthenticated(false);
        setReady(true);
      });

    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.access_token) setToken(session.access_token);
      else clearToken();
      setAuthenticated(Boolean(session?.access_token));
      setReady(true);
    });

    const unauthorized = () => setAuthenticated(false);
    window.addEventListener("heard:unauthorized", unauthorized);
    return () => {
      active = false;
      data.subscription.unsubscribe();
      window.removeEventListener("heard:unauthorized", unauthorized);
    };
  }, []);

  return { ready, authenticated };
}

function SessionGate({ children }: { children: JSX.Element }) {
  const { ready, authenticated } = useSessionState();
  const location = useLocation();

  if (!ready) {
    return (
      <div className="session-check" role="status">
        <span className="wordmark">HEARD</span>
        <span>Restoring your workspace…</span>
      </div>
    );
  }

  if (!authenticated) return <Navigate to="/login" state={{ from: location }} replace />;
  return children;
}

export default function App() {
  const workspace = (
    <SessionGate>
      <HeardWorkspace />
    </SessionGate>
  );

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Navigate to="/pre-training" replace />} />
      <Route path="/pre-training/*" element={workspace} />
      <Route path="/post-training/*" element={workspace} />
      <Route path="/leaderboard/*" element={workspace} />
      <Route path="/dms/*" element={workspace} />
      <Route path="*" element={<Navigate to="/pre-training" replace />} />
    </Routes>
  );
}
