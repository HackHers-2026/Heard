"""TigerTable integration (https://tigertable.com).

Intended use in Heard: push each completed practice (scores, domain, improvement
delta) into a TigerTable table so we get sharable, structured analytics and can
build the leaderboard / progress-over-time views on top of it.

INTEGRATION STATUS: exploratory. Confirm the real API surface before relying on
this. For now this module mirrors rows locally and no-ops the remote call when
TIGERTABLE_API_KEY is unset.
"""
from __future__ import annotations

import httpx

from app.config import settings

# Local mirror for dev / demo.
_rows: list[dict] = []


async def sync_practice(row: dict) -> None:
    """Upsert a completed-practice row into TigerTable.

    Expected row keys: user_id, display_name, domain, score, improvement_score,
    session_id, created_at.
    """
    _rows.append(row)
    if not settings.tigertable_api_key:
        return

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.tigertable_base_url}/v1/rows",
            headers={"Authorization": f"Bearer {settings.tigertable_api_key}"},
            json={"table": "practices", "row": row},
        )
        resp.raise_for_status()


def local_rows() -> list[dict]:
    """Expose the local mirror (used by dashboards during the hackathon)."""
    return _rows
