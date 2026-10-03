"""Retention: archive old events so the crisis list stays bounded.

Archive, never delete: rows are flagged is_active=False (the list endpoint
only serves active rows) and kept, so history/trend features can use them
later. GDELT adds ~11k events/day, and nothing used to expire them."""
import logging
from datetime import datetime, timedelta

from sqlalchemy import or_

from models import Session, Crisis

logger = logging.getLogger(__name__)

# Matches the longest range the UI offers (7d) — nothing the list can show
# is archived out from under it.
ARCHIVE_AFTER_DAYS = 7


def archive_old_crises(days=ARCHIVE_AFTER_DAYS):
    """Flag active events older than `days` as inactive. Leaves curated
    entries and anything scheduled in advance (elections, summits —
    `date_scheduled` set / status 'upcoming') alone, since their date_start
    is the ingestion time, not when they matter. Returns the number archived.
    Idempotent."""
    session = Session()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        archived = (
            session.query(Crisis)
            .filter(
                Crisis.is_active == True,  # noqa: E712 — SQL comparison
                Crisis.date_start < cutoff,
                or_(Crisis.source.is_(None), Crisis.source != 'CURATED'),
                Crisis.date_scheduled.is_(None),
                Crisis.status != 'upcoming',
            )
            .update({Crisis.is_active: False}, synchronize_session=False)
        )
        session.commit()
        if archived:
            logger.info(f"Archived {archived} crises older than {days} days")
        return archived
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
