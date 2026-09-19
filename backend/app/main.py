"""Heard backend — one API serving both frontends (web app + Chrome extension).

Run locally:
    cd backend
    python -m venv .venv && .venv\\Scripts\\activate   # (Windows)
    pip install -r requirements.txt
    cp .env.example .env   # then fill in keys
    uvicorn app.main:app --reload

Interactive docs: http://localhost:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import auth, feedback, leaderboard, messages, sessions, training


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Heard API",
    version="0.1.0",
    description="Empowering women to be Heard — practice, live AI feedback, and growth.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(feedback.router)
app.include_router(leaderboard.router)
app.include_router(messages.router)
app.include_router(training.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "heard-api"}
