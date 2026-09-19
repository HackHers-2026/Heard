# Task 13 — Stretch: TigerTable Analytics

**Status:** stretch — after 10PM  
**Owner:** backend/app/services/ + new analytics router

---

## Goal

Stream speech events (segment posted, speech ended, score computed) to TigerTable for real-time leaderboard aggregation and profile averages.

---

## Events to stream

| Event | Payload |
|-------|---------|
| `speech.ended` | user_id, speech_id, overall score, career_tag |
| `segment.posted` | speech_id, pace_wpm, avg_volume, filler_pct |
| `post.liked` | post_id, user_id, career_tag |

---

## Integration point

Add `tigertable.track(event, payload)` calls inside existing service functions:
- `gemini._save_metrics()` → emit `speech.ended`
- `speech` router `/segment` → emit `segment.posted`
- `feed` router `/like` → emit `post.liked`

---

## New env var
```
TIGERTABLE_API_KEY=<from TigerTable dashboard>
```

Stub: if key not set, `track()` is a no-op — never crashes local dev.

---

## Stretch analytics queries

- Top speeches by career_tag (leaderboard)
- Rolling average pace/volume trends per user
- Community engagement (likes per post by tag)
