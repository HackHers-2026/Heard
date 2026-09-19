from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import encourage, speech, feed, profile, mentor, chat


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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(encourage.router)
app.include_router(speech.router)
app.include_router(feed.router)
app.include_router(profile.router)
app.include_router(mentor.router)
app.include_router(chat.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
