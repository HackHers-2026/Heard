"""Channel service — seed, list, membership."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.errors import APIError
from app.models import Channel, ChannelMembership

# Seed set — order matters for a stable sidebar.
SEED_CHANNELS = [
    ("technology", "Technology", "Practice technical talks, demos and architecture reviews."),
    ("finance", "Finance", "Pitch numbers, strategy and financial narratives with clarity."),
    ("law", "Law", "Sharpen argument structure and precise, persuasive delivery."),
    ("marketing", "Marketing", "Tell brand and product stories that land."),
    ("healthcare", "Healthcare", "Communicate complex care and research clearly."),
    ("education", "Education", "Explain, teach and present with confidence."),
    ("general", "General", "Everyday speaking practice across any topic."),
]


def seed_channels(session: Session) -> int:
    """Insert missing seed channels. Idempotent — safe to run repeatedly."""
    created = 0
    for slug, name, description in SEED_CHANNELS:
        exists = session.exec(select(Channel).where(Channel.slug == slug)).first()
        if not exists:
            session.add(Channel(slug=slug, name=name, description=description))
            created += 1
    if created:
        session.commit()
    return created


def list_channels(session: Session) -> list[Channel]:
    return list(session.exec(select(Channel).order_by(Channel.created_at, Channel.name)).all())


def get_channel(channel_id: str, session: Session) -> Channel:
    channel = session.get(Channel, channel_id)
    if not channel:
        # Allow lookup by slug too, for friendlier URLs.
        channel = session.exec(select(Channel).where(Channel.slug == channel_id)).first()
    if not channel:
        raise APIError(404, "CHANNEL_NOT_FOUND", "Channel was not found.")
    return channel


def is_member(user_id: str, channel_id: str, session: Session) -> bool:
    return session.exec(
        select(ChannelMembership).where(
            ChannelMembership.user_id == user_id,
            ChannelMembership.channel_id == channel_id,
        )
    ).first() is not None


def join_channel(user_id: str, channel_id: str, session: Session) -> ChannelMembership:
    channel = get_channel(channel_id, session)
    existing = session.exec(
        select(ChannelMembership).where(
            ChannelMembership.user_id == user_id,
            ChannelMembership.channel_id == channel.id,
        )
    ).first()
    if existing:
        return existing
    membership = ChannelMembership(user_id=user_id, channel_id=channel.id)
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return membership


def leave_channel(user_id: str, channel_id: str, session: Session) -> None:
    channel = get_channel(channel_id, session)
    existing = session.exec(
        select(ChannelMembership).where(
            ChannelMembership.user_id == user_id,
            ChannelMembership.channel_id == channel.id,
        )
    ).first()
    if existing:
        session.delete(existing)
        session.commit()


def my_channels(user_id: str, session: Session) -> list[Channel]:
    rows = session.exec(
        select(Channel)
        .join(ChannelMembership, ChannelMembership.channel_id == Channel.id)
        .where(ChannelMembership.user_id == user_id)
        .order_by(Channel.name)
    ).all()
    return list(rows)


def serialize_channel(channel: Channel, *, joined: Optional[bool] = None) -> dict:
    data = {
        "id": channel.id,
        "slug": channel.slug,
        "name": channel.name,
        "description": channel.description,
        "created_at": channel.created_at,
    }
    if joined is not None:
        data["joined"] = joined
    return data
