from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.database import init_db, engine
from app.errors import register_error_handlers
from app.routers import encourage, speech, feed, profile, mentor, chat, stt
from app.routers import auth, channels, threads, sessions, leaderboard, dms
from app.services.channels import seed_channels


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Idempotent channel seed — safe to run on every startup.
    with Session(engine) as session:
        seed_channels(session)
    yield


app = FastAPI(
    title="Heard API",
    version="0.2.0",
    description="Empowering women to be Heard — practice, live AI feedback, and growth.",
    lifespan=lifespan,
)

register_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Legacy routers (extension + original web flows).
app.include_router(encourage.router)
app.include_router(speech.router)
app.include_router(feed.router)
app.include_router(profile.router)
app.include_router(mentor.router)
app.include_router(chat.router)
app.include_router(stt.router)

# Heard v2 routers (auth, channels, training, leaderboard, DMs).
app.include_router(auth.router)
app.include_router(channels.router)
app.include_router(threads.router)
app.include_router(sessions.router)
app.include_router(leaderboard.router)
app.include_router(dms.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
