import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { clearToken, getToken } from "./api";
import { supabase } from "./supabase";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import SessionChat from "./pages/SessionChat";
import Leaderboard from "./pages/Leaderboard";
import Messages from "./pages/Messages";
import PreTraining from "./pages/PreTraining";

function RequireAuth({ children }: { children: JSX.Element }) {
  const location = useLocation();
  if (!getToken()) return <Navigate to="/login" state={{ from: location }} replace />;
  return children;
}

function Nav() {
  if (!getToken()) return null;

  async function logout() {
    // Sign out of Supabase too — the extension bridge watches the Supabase
    // session, so clearing only heard_token would leave the user "signed in".
    await supabase.auth.signOut();
    clearToken();
    location.href = "/login";
  }

  return (
    <nav className="nav">
      <Link to="/" className="brand">Heard</Link>
      <div className="nav-links">
        <Link to="/">Dashboard</Link>
        <Link to="/train">Pre-Training</Link>
        <Link to="/leaderboard">Leaderboard</Link>
        <Link to="/messages">Messages</Link>
        <button onClick={logout}>Log out</button>
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <>
      <Nav />
      <main className="container">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<RequireAuth><Dashboard /></RequireAuth>} />
          <Route path="/session/:id" element={<RequireAuth><SessionChat /></RequireAuth>} />
          <Route path="/train" element={<RequireAuth><PreTraining /></RequireAuth>} />
          <Route path="/leaderboard" element={<RequireAuth><Leaderboard /></RequireAuth>} />
          <Route path="/messages" element={<RequireAuth><Messages /></RequireAuth>} />
        </Routes>
      </main>
    </>
  );
}
