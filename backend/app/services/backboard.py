"""Backboard memory layer.

Backboard stores the long-running conversation/memory for each user's Gemini
coaching thread, so feedback references *past* practices ("last time you used
a lot of filler words — this run was much cleaner"). Each PracticeSession is
linked to a Backboard thread id.

If BACKBOARD_API_KEY is unset, we fall back to an in-process memory dict so the
rest of the app keeps working during local dev.

Docs: https://backboard.io (confirm exact endpoints when integrating).
"""
from __future__ import annotations

import uuid

import httpx

from app.config import settings

# In-memory fallback: {thread_id: [ {role, content}, ... ]}
_local_memory: dict[str, list[dict]] = {}


async def create_thread(user_id: int, domain: str) -> str:
    """Create a memory thread for a user's domain-specific coaching."""
    if not settings.backboard_api_key:
        thread_id = f"local-{user_id}-{uuid.uuid4().hex[:8]}"
        _local_memory[thread_id] = []
        return thread_id

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.backboard_base_url}/threads",
            headers={"Authorization": f"Bearer {settings.backboard_api_key}"},
            json={"metadata": {"user_id": user_id, "domain": domain}},
        )
        resp.raise_for_status()
        return resp.json()["id"]


async def append_memory(thread_id: str, role: str, content: str) -> None:
    """Persist a turn (user speech or AI feedback) to the thread."""
    if not settings.backboard_api_key:
        _local_memory.setdefault(thread_id, []).append({"role": role, "content": content})
        return

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.backboard_base_url}/threads/{thread_id}/messages",
            headers={"Authorization": f"Bearer {settings.backboard_api_key}"},
            json={"role": role, "content": content},
        )
        resp.raise_for_status()


async def get_memory(thread_id: str) -> list[dict]:
    """Fetch prior turns to prime Gemini with context."""
    if not settings.backboard_api_key:
        return _local_memory.get(thread_id, [])

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{settings.backboard_base_url}/threads/{thread_id}/messages",
            headers={"Authorization": f"Bearer {settings.backboard_api_key}"},
        )
        resp.raise_for_status()
        return resp.json().get("messages", [])
