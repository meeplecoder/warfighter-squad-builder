"""Cleanup of custom mission cards (module 'Custom') that no squad uses any more.

Orphans appear when a squad is deleted or switches mission, or when a mission made in the
builder is replaced / never saved with a squad. See spec/08_squad_tools.md §6.

- purge(card_ids)  — immediate, for the cards a request just unlinked.
- purge()          — sweep: orphans older than GRACE_HOURS (so a mission created in a
                     builder that hasn't been saved yet survives).
"""
from datetime import datetime, timedelta, timezone

from app import db
from app.models import Card, Squad, CUSTOM_MODULE

GRACE_HOURS = 24


def purge(card_ids=None, owner_id=None):
    """Delete unreferenced custom missions; returns how many were deleted. Caller commits."""
    used = db.session.query(Squad.mission_card_id)
    query = Card.query.filter(Card.module == CUSTOM_MODULE, ~Card.id.in_(used))
    if card_ids is not None:
        ids = [i for i in card_ids if i]
        if not ids:
            return 0
        query = query.filter(Card.id.in_(ids))
        if owner_id is not None:
            query = query.filter(Card.owner_user_id == owner_id)
    else:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=GRACE_HOURS)).strftime('%Y-%m-%dT%H:%M:%SZ')
        query = query.filter((Card.created_at.is_(None)) | (Card.created_at < cutoff))
    orphans = query.all()
    for c in orphans:
        db.session.delete(c)
    return len(orphans)
