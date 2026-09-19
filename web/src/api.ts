// API client for the Heard backend (see docs/contracts.md).
// All routes are under /api/* and authenticated with the live Supabase token.
import { supabase } from "./supabase";

const BASE = "/api";
const TOKEN_KEY = "heard_token";

// heard_token is only a lightweight "logged in" flag for route gating.
// The actual bearer token is pulled live from the Supabase session per request
// (so it never goes stale as Supabase rotates it).
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function authHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token ?? getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function currentUserId(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.user?.id ?? null;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(await authHeader()),
    ...(options.headers as Record<string, string>),
  };
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export type Phase = "preptalk" | "activetalk" | "talksummary";
export type CareerTag = "engineering" | "finance" | "marketing" | "law";

export const api = {
  // --- Pre-speech encouragement ---
  encourage: (mode: "quick" | "plan", context?: string) =>
    request<{ message: string; outline?: string[] }>("/encourage", {
      method: "POST",
      body: JSON.stringify({ mode, context }),
    }),

  // --- Speech session ---
  startSpeech: () =>
    request<{ speech_id: string; session_token: string }>("/speech/start", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  endSpeech: (speechId: string) =>
    request<{ report_ready: boolean }>("/speech/end", {
      method: "POST",
      body: JSON.stringify({ speech_id: speechId }),
    }),
  report: (speechId: string) => request<any>(`/speech/${speechId}/report`),

  // --- AI coach chat (per speech) ---
  postChat: (speechId: string, message: string, phase: Phase) =>
    request<{ reply: string; phase: string; summary: string }>(`/speech/${speechId}/chat`, {
      method: "POST",
      body: JSON.stringify({ message, phase }),
    }),
  getChat: (speechId: string, phase?: Phase) =>
    request<{ messages: any[] }>(`/speech/${speechId}/chat${phase ? `?phase=${phase}` : ""}`),

  // --- Community feed ---
  feed: (careerTag?: string) =>
    request<{ posts: any[]; next_cursor: string | null }>(
      `/feed${careerTag ? `?career_tag=${encodeURIComponent(careerTag)}` : ""}`
    ),
  like: (postId: string) =>
    request<{ liked: boolean; like_count: number }>(`/feed/${postId}/like`, { method: "POST" }),

  // --- Profile ---
  profile: (userId: string) => request<any>(`/profile/${userId}`),

  // --- Mentor ---
  mentorConnect: (mentorId: string, speechId: string) =>
    request<any>("/mentor/connect", {
      method: "POST",
      body: JSON.stringify({ mentor_id: mentorId, speech_id: speechId }),
    }),
};
