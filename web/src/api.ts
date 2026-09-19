// Thin API client for the Heard backend. Uses the Vite proxy (/api -> :8000).
const BASE = "/api";
const TOKEN_KEY = "heard_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export type Domain = "tech" | "law" | "finance" | "marketing";

export const api = {
  signup: (body: Record<string, unknown>) =>
    request<{ access_token: string }>("/auth/signup", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  login: async (email: string, password: string) => {
    // OAuth2 password flow expects form-encoded body.
    const res = await fetch(`${BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email, password }),
    });
    if (!res.ok) throw new Error("Login failed");
    return (await res.json()) as { access_token: string };
  },

  me: () => request<any>("/auth/me"),
  sessions: () => request<any[]>("/sessions"),
  createSession: (body: Record<string, unknown>) =>
    request<any>("/sessions", { method: "POST", body: JSON.stringify(body) }),
  sessionFeedback: (id: number) => request<any[]>(`/sessions/${id}/feedback`),
  summarize: (id: number) =>
    request<any>(`/feedback/summarize?session_id=${id}`, { method: "POST" }),
  leaderboard: (domain: Domain) => request<any[]>(`/leaderboard/${domain}`),
  mentors: (domain: Domain) => request<any[]>(`/leaderboard/${domain}/mentors`),
  preTraining: (domain: Domain) => request<any>(`/training/pre/${domain}`),
  sendMessage: (recipient_id: number, bodyText: string) =>
    request<any>("/messages", {
      method: "POST",
      body: JSON.stringify({ recipient_id, body: bodyText }),
    }),
  thread: (otherId: number) => request<any[]>(`/messages/thread/${otherId}`),
};
