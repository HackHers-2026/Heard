import { supabase } from "./supabase";

const configuredBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();
const API_BASE = configuredBase ? configuredBase.replace(/\/+$/, "") : "";
const TOKEN_KEY = "heard_token";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function accessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? getToken();
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as {
      error?: { code?: string; message?: string };
      detail?: string;
    };
    return new ApiError(
      response.status,
      body.error?.code ?? `HTTP_${response.status}`,
      body.error?.message ?? body.detail ?? "The request could not be completed.",
    );
  } catch {
    return new ApiError(response.status, `HTTP_${response.status}`, "The request could not be completed.");
  }
}

async function request<T>(path: string, options: RequestInit = {}, retryAuth = true): Promise<T> {
  const token = await accessToken();
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Couldn’t reach Heard. Check your connection and try again.");
  }

  if (response.status === 401) {
    if (retryAuth) {
      try {
        const { data } = await supabase.auth.refreshSession();
        if (data.session?.access_token) {
          setToken(data.session.access_token);
          return request<T>(path, options, false);
        }
      } catch {
        // Fall through to a clean signed-out state below.
      }
    }
    await supabase.auth.signOut({ scope: "local" }).catch(() => undefined);
    clearToken();
    window.dispatchEvent(new CustomEvent("heard:unauthorized"));
  }

  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export type Profile = {
  id: string;
  display_name: string | null;
  username: string | null;
  avatar_url: string | null;
  bio?: string | null;
  is_private?: boolean;
};

export type CurrentUser = {
  user: { id: string; name: string };
  profile: Profile;
};

export type Channel = {
  id: string;
  slug: string;
  name: string;
  description: string;
  created_at: string;
  joined?: boolean;
};

export type ThreadType = "PRE_TRAINING" | "POST_TRAINING";
export type SenderType = "user" | "assistant" | "system" | "transcript";

export type ChatThread = {
  id: string;
  user_id: string;
  channel_id: string;
  thread_type: ThreadType;
  session_id: string | null;
  title: string;
  created_at: string;
  updated_at: string;
};

export type ThreadMessage = {
  id: string;
  thread_id: string;
  sender_type: SenderType;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type SessionStatus = "ACTIVE" | "PROCESSING" | "COMPLETED" | "FAILED";

export type TrainingSession = {
  id: string;
  user_id: string;
  channel_id: string;
  title: string;
  status: SessionStatus;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number;
  total_words: number;
  created_at: string;
};

export type MetricScores = {
  clarity: number | null;
  conciseness: number | null;
  pace: number | null;
  volume: number | null;
  confidence: number | null;
  structure: number | null;
};

export type CoachingMoment = {
  segment_index: number | null;
  timestamp_start: number | null;
  timestamp_end: number | null;
  evidence: string;
  reason: string;
};

export type PriorityMoment = CoachingMoment & {
  dimension: string;
  recommendation: string;
};

export type DimensionChange = {
  dimension: string;
  previous: number | null;
  current: number | null;
  explanation: string;
  evidence: string;
};

export type PerformancePattern = {
  pattern: string;
  sessions_observed: number | null;
  trend: string;
  explanation: string;
};

export type SessionGoal = {
  goal: string;
  reason: string;
  measurement: string;
};

export type HistoricalSummary = {
  baseline_overall_score: number | null;
  previous_overall_score: number | null;
  current_overall_score: number | null;
  improvement_from_baseline_percent: number | null;
};

export type LongitudinalAnalysis = {
  improvements_since_previous?: DimensionChange[];
  regressions_since_previous?: DimensionChange[];
  historical_summary?: HistoricalSummary;
};

export type SessionFeedback = {
  id: string;
  session_id: string;
  scores: MetricScores;
  overall_score: number | null;
  unavailable_dimensions: string[];
  filler_count: number;
  filler_rate: number;
  average_wpm: number;
  volume_consistency: number | null;
  summary: string;
  strengths: string[];
  improvements: string[];
  strongest_moments: CoachingMoment[];
  priority_moments: PriorityMoment[];
  persistent_patterns: PerformancePattern[];
  new_patterns: PerformancePattern[];
  stable_strengths: string[];
  next_session_goals: SessionGoal[];
  metrics_interpretation: Record<string, unknown>;
  vocal_variety: Record<string, unknown>;
  metrics_summary: Record<string, unknown>;
  longitudinal_analysis: LongitudinalAnalysis;
  created_at: string;
};

export type TranscriptSegment = {
  id: string;
  session_id: string;
  segment_index: number;
  transcript: string;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  word_count: number;
  audio_metrics: Record<string, unknown>;
  created_at: string;
};

export type ImprovementSummary = {
  channel_id: string;
  baseline_score: number | null;
  recent_score: number | null;
  improvement_percent: number | null;
  completed_session_count: number;
  completed_sessions: number;
  dimension_trends: Record<string, { baseline: number | null; recent: number | null; delta: number | null }>;
  performance_profile?: Record<string, unknown> | null;
};

export type LeaderboardEntry = {
  user_id: string;
  username: string | null;
  display_name: string | null;
  avatar_url: string | null;
  improvement_percent: number;
  completed_sessions: number;
  rank: number;
};

export type LeaderboardResponse = {
  channel_id: string;
  total: number;
  entries: LeaderboardEntry[];
  viewer_rank: LeaderboardEntry | null;
};

export type DMMessage = {
  id: string;
  conversation_id: string;
  sender_id: string;
  content: string;
  created_at: string;
  read_at: string | null;
};

export type DMConversation = {
  id: string;
  updated_at: string;
  other_user: {
    user_id: string;
    display_name: string | null;
    username: string | null;
    avatar_url: string | null;
  } | null;
  last_message: DMMessage | null;
  unread_count: number;
};

export type SessionDetail = {
  session: TrainingSession;
  thread: ChatThread | null;
  feedback: SessionFeedback | null;
  progress: ImprovementSummary;
  recommended_peers: LeaderboardEntry[];
};

export const api = {
  me: () => request<CurrentUser>("/api/auth/me"),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  updateProfile: (data: Partial<Pick<Profile, "display_name" | "username" | "avatar_url" | "bio" | "is_private">>) =>
    request<{ profile: Profile }>("/api/auth/profile", { method: "PATCH", body: JSON.stringify(data) }),

  channels: () => request<{ channels: Channel[] }>("/api/channels"),
  channel: (channelId: string) => request<{ channel: Channel }>(`/api/channels/${encodeURIComponent(channelId)}`),
  joinChannel: (channelId: string) =>
    request<{ channel: Channel }>(`/api/channels/${encodeURIComponent(channelId)}/join`, { method: "POST" }),

  preTrainingThreads: (channelId: string) =>
    request<{ threads: ChatThread[] }>(`/api/channels/${encodeURIComponent(channelId)}/pre-training/threads`),
  createPreTrainingThread: (channelId: string, data: { title?: string; message?: string } = {}) =>
    request<{ thread: ChatThread; messages: ThreadMessage[] }>(
      `/api/channels/${encodeURIComponent(channelId)}/pre-training/threads`,
      { method: "POST", body: JSON.stringify(data) },
    ),
  thread: (threadId: string) =>
    request<{ thread: ChatThread; messages: ThreadMessage[] }>(`/api/threads/${encodeURIComponent(threadId)}`),
  postThreadMessage: (threadId: string, content: string) =>
    request<{ message: ThreadMessage; reply: ThreadMessage }>(`/api/threads/${encodeURIComponent(threadId)}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  channelSessions: (channelId: string) =>
    request<{ sessions: TrainingSession[] }>(`/api/channels/${encodeURIComponent(channelId)}/sessions`),
  createSession: (channelId: string, title?: string) =>
    request<{ session: TrainingSession; thread: ChatThread; session_id: string; thread_id: string }>(
      `/api/channels/${encodeURIComponent(channelId)}/sessions`,
      { method: "POST", body: JSON.stringify({ title: title || undefined }) },
    ),
  addSessionSegment: (
    sessionId: string,
    data: {
      segment_index: number;
      transcript: string;
      start_seconds: number;
      end_seconds: number;
      duration_seconds?: number;
      audio_metrics?: Record<string, unknown>;
    },
  ) =>
    request<{ segment: TranscriptSegment }>(`/api/sessions/${encodeURIComponent(sessionId)}/segments`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  completeSession: (sessionId: string) =>
    request<{ session: TrainingSession; feedback: SessionFeedback; recommended_peers: LeaderboardEntry[] }>(
      `/api/sessions/${encodeURIComponent(sessionId)}/complete`,
      { method: "POST" },
    ),
  session: (sessionId: string) => request<SessionDetail>(`/api/sessions/${encodeURIComponent(sessionId)}`),
  sessionSegments: (sessionId: string) =>
    request<{ segments: TranscriptSegment[] }>(`/api/sessions/${encodeURIComponent(sessionId)}/segments`),
  progress: (channelId: string) =>
    request<ImprovementSummary>(`/api/me/channels/${encodeURIComponent(channelId)}/progress`),

  leaderboard: (channelId: string) =>
    request<LeaderboardResponse>(`/api/channels/${encodeURIComponent(channelId)}/leaderboard`),
  recommendedPeers: (channelId: string) =>
    request<{ peers: LeaderboardEntry[] }>(`/api/channels/${encodeURIComponent(channelId)}/recommended-peers`),

  conversations: () => request<{ conversations: DMConversation[] }>("/api/dms"),
  openConversation: (userId: string) =>
    request<{ conversation_id: string; created_at: string }>(`/api/dms/with/${encodeURIComponent(userId)}`, { method: "POST" }),
  dmMessages: (conversationId: string, limit = 100, offset = 0) =>
    request<{ messages: DMMessage[] }>(
      `/api/dms/${encodeURIComponent(conversationId)}/messages?limit=${limit}&offset=${offset}`,
    ),
  sendDM: (conversationId: string, content: string) =>
    request<{ message: DMMessage }>(`/api/dms/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  markDMRead: (conversationId: string) =>
    request<{ marked_read: number }>(`/api/dms/${encodeURIComponent(conversationId)}/read`, { method: "POST" }),
};
