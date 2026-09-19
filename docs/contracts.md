# Contracts — Data Models & API Interfaces

**Read this before writing any code.** These are the shared types and routes all 3 parts of the system depend on. If you need to change something here, align with the team first.

---

## Data models

### User
```ts
{
  id: string                  // Supabase UUID
  linkedin_id: string
  name: string
  avatar_url: string
  career_tag: string          // e.g. "engineering", "marketing"
  is_mentor: boolean          // toggled on profile
  created_at: string
}
```

### Speech
```ts
{
  id: string
  user_id: string
  status: "live" | "done"
  started_at: string
  ended_at: string | null
}
```

### SpeechMetrics
```ts
{
  id: string
  speech_id: string
  clarity: number             // 0–100
  volume: number              // 0–100
  pace: number                // 0–100
  confidence: number          // 0–100
  structure: number           // 0–100
  overall: number             // 0–100, computed average
  summary: string             // short AI-generated summary
  suggestions: string[]       // 2–3 actionable improvements
  mentor_suggestions: UserId[] // users with high scores on weak metrics + mentor toggle on
}
```

### RealtimeSegment
```ts
{
  id: string
  speech_id: string
  transcript: string          // ~2 min of speech text
  nudge: string               // ≤10 words, e.g. "Slow down a little"
  segment_index: number       // 0-based, order within the speech
  recorded_at: string         // segment start timestamp (ISO)
  duration_seconds: number    // segment length → WPM = word_count / (duration_seconds / 60)
  avg_volume: number          // 0–100, mean amplitude over segment (Web Audio API)
  volume_variance: number     // 0–100, amplitude std dev — high = unsteady volume
}
```

> **Chrome extension:** requires two parallel streams — `SpeechRecognitionAPI` for transcript + `AudioContext` / `AnalyserNode` for amplitude sampling. Both must be active for the full 2-min window before sending the segment.

### CommunityPost
```ts
{
  id: string
  speech_id: string
  user_id: string
  is_public: boolean
  career_tag: string
  topic_tag: string
  like_count: number          // denormalised for feed performance
  created_at: string
}
```

### Like
```ts
{
  id: string
  post_id: string
  user_id: string
  created_at: string
}
```

### MentorConnection
```ts
{
  id: string
  requester_id: string
  mentor_id: string
  speech_id: string           // the speech that triggered the suggestion
  status: "pending" | "accepted" | "declined"
  created_at: string
}
```

### ChatMessage
```ts
{
  id: string
  session_hash: string        // sha256(speech_id)[:16] — stable conversation key
  speech_id: string | null
  role: "user" | "model"
  phase: "preptalk" | "activetalk" | "talksummary"
  content: string
  summary: string             // 3-5 word label, e.g. "asked about opening line"
  created_at: string
}
```

---

## API routes

### POST /api/encourage
Pre-speech encouragement — quick button or speech planner.
```ts
// request
{ mode: "quick" | "plan", context?: string }

// response
{ message: string, outline?: string[] }  // outline only in "plan" mode
```

### POST /api/speech/start
Begin a speech session. Called by the webapp; session token passed to the Chrome extension.
```ts
// request (authenticated)
{}

// response
{ speech_id: string, session_token: string }
```

### POST /api/speech/segment
Submit a 2-min transcript chunk from the Chrome extension, get a nudge back.
```ts
// request (bearer: session_token)
{
  speech_id: string
  transcript: string
  segment_index: number
  recorded_at: string       // segment start (ISO)
  duration_seconds: number
  avg_volume: number        // 0–100
  volume_variance: number   // 0–100
}

// response
{ nudge: string }  // ≤10 words
```

### POST /api/speech/end
Close the session and trigger full Gemini analysis. Chrome calls this when the user stops recording.
```ts
// request (bearer: session_token)
{ speech_id: string }

// response
{ report_ready: boolean }  // analysis is async; poll or use Supabase realtime
```

### GET /api/speech/:id/report
Fetch the completed post-speech report.
```ts
// response
{ speech: Speech, metrics: SpeechMetrics }
```

### GET /api/feed
Paginated community feed.
```ts
// query params: ?career_tag=&topic_tag=&cursor=&limit=20

// response
{ posts: (CommunityPost & { user: User, metrics: SpeechMetrics })[], next_cursor: string | null }
```

### POST /api/feed/:id/like
Toggle like on a community post.
```ts
// response
{ liked: boolean, like_count: number }
```

### GET /api/profile/:userId
User profile with top-3 speech averages for the radar chart.
```ts
// response
{
  user: User,
  top_speeches: Speech[],         // up to 3, outliers excluded
  average_metrics: {              // averaged across top_speeches
    clarity: number, volume: number, pace: number,
    confidence: number, structure: number, overall: number
  }
}
```

### POST /api/speech/:id/chat
Send a message to the AI coach for this speech session. Gemini responds in context of the last 5 exchanges.
```ts
// request
{ message: string, phase: "preptalk" | "activetalk" | "talksummary" }

// response
{ reply: string, phase: string, summary: string }   // summary = 3-5 word label
```

### GET /api/speech/:id/chat
Fetch the full conversation thread for a speech session.
```ts
// query params: ?phase=preptalk  (optional filter)

// response
{ messages: ChatMessage[] }
```

### POST /api/mentor/connect
Send a mentor connection request, triggered from the post-speech report.
```ts
// request
{ mentor_id: string, speech_id: string }

// response
{ connection: MentorConnection }
```

---

## Supabase tables

| Table | Maps to |
|-------|---------|
| `user` | User |
| `speech` | Speech |
| `speechmetrics` | SpeechMetrics |
| `realtimesegment` | RealtimeSegment |
| `communitypost` | CommunityPost |
| `like` | Like |
| `mentorconnection` | MentorConnection |
| `chatmessage` | ChatMessage |

Analytics / aggregated stats come from TigerData → Supabase. See [TigerData Supabase docs](https://www.tigerdata.com/docs/integrate/data-engineering-etl/supabase).

---

## Decisions

- **Nudge delivery** — synchronous: returned in `/api/speech/segment` response; Chrome extension caches it locally
- **Scores** — integers 0–100
- **Chrome ↔ webapp auth handoff** — URL-based: after installing the extension, user logs in via a webapp popup window; extension receives the session token from that flow
- **Report timing** — segment nudges are sync (drop if latency too high); final post-speech report is async, frontend subscribes via Supabase realtime
- **Auth for POC** — Supabase email magic link; LinkedIn OAuth via Auth0 is stretch (after 10PM)
- **Profile aggregation for POC** — simple Supabase query over top-3 speeches; TigerData pipeline is stretch (after 10PM)
