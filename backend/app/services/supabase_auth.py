"""Thin proxy over Supabase Auth (GoTrue) for signup / login / logout.

The backend never mints its own tokens — Supabase is the identity provider.
These helpers forward credentials to the Supabase Auth REST API using the
anon/publishable key. Token *verification* on protected routes stays in
``app.dependencies.get_current_user``.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings
from app.errors import APIError

logger = logging.getLogger("heard.supabase_auth")


def _anon_key() -> str:
    return settings.supabase_anon_key or settings.supabase_publishable_key


def _base() -> str:
    if not settings.supabase_url:
        raise APIError(503, "AUTH_UNAVAILABLE", "Authentication is not configured.")
    return settings.supabase_url.rstrip("/")


def _headers() -> dict:
    return {"apikey": _anon_key(), "Content-Type": "application/json"}


def _post(path: str, json: dict, *, token: Optional[str] = None) -> httpx.Response:
    headers = _headers()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        return httpx.post(f"{_base()}{path}", json=json, headers=headers, timeout=10)
    except httpx.HTTPError:
        logger.exception("supabase auth request failed: %s", path)
        raise APIError(502, "AUTH_UPSTREAM_ERROR", "Authentication service is unavailable.")


def _error_from(resp: httpx.Response, default_code: str) -> APIError:
    try:
        body = resp.json()
        msg = body.get("msg") or body.get("error_description") or body.get("error") or "Authentication failed."
    except Exception:
        msg = "Authentication failed."
    status = 401 if resp.status_code in (400, 401, 403) else 502
    return APIError(status, default_code, msg)


def signup(email: str, password: str, display_name: Optional[str] = None) -> dict:
    payload = {"email": email, "password": password}
    if display_name:
        payload["data"] = {"display_name": display_name}
    resp = _post("/auth/v1/signup", payload)
    if resp.status_code >= 400:
        raise _error_from(resp, "SIGNUP_FAILED")
    return resp.json()


def login(email: str, password: str) -> dict:
    resp = _post("/auth/v1/token?grant_type=password", {"email": email, "password": password})
    if resp.status_code >= 400:
        raise _error_from(resp, "LOGIN_FAILED")
    return resp.json()


def logout(token: str) -> None:
    resp = _post("/auth/v1/logout", {}, token=token)
    if resp.status_code >= 400 and resp.status_code not in (401, 403, 404):
        raise _error_from(resp, "LOGOUT_FAILED")
