"""Enrich recommendations with reviewed official-source operating hours.

No website scraping, no guessed schedules, no Google Places content persisted.
An editor must inspect an official venue page before populating the ledger.
Absent, stale, or malformed records are deliberately treated as unknown.
"""
import asyncio
import logging
import os
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

logger = logging.getLogger(__name__)
MAX_OFFICIAL_HOURS = 10
MAX_RECORD_AGE_DAYS = 30


def _official_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.hostname)


def _lookup(candidates):
    from .database import require_db_url
    import psycopg
    from psycopg.rows import dict_row
    keys = []
    for c in candidates[:MAX_OFFICIAL_HOURS]:
        if c.source == "curated" and ":" in c.place_id:
            keys.append(tuple(c.place_id.split(":", 1)))
    if not keys:
        return {}
    with psycopg.connect(require_db_url(), row_factory=dict_row, connect_timeout=8) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.activity_official_hours') IS NOT NULL AS present")
            if not cursor.fetchone()["present"]:
                return {}
            placeholders = ",".join("(%s,%s)" for _ in keys)
            params = [p for pair in keys for p in pair]
            cursor.execute(
                "SELECT source_id, activity_id, weekly_hours, date_notices, "
                "source_url, verified_at, valid_until FROM public.activity_official_hours "
                f"WHERE (source_id,activity_id) IN ({placeholders})",
                params,
            )
            return {(row["source_id"], row["activity_id"]): row for row in cursor.fetchall()}


def apply_official_hours(candidates, rows, visit_date=None, today=None):
    """Prefer fresh official weekly descriptions; dated notices are informational."""
    now = datetime.now(timezone.utc)
    local_today = today or now.astimezone(ZoneInfo("America/Edmonton")).date()
    selected = visit_date or local_today
    updated = []
    for c in candidates:
        key = tuple(c.place_id.split(":", 1)) if c.source == "curated" and ":" in c.place_id else None
        row = rows.get(key)
        if not row:
            updated.append(c)
            continue
        checked = row.get("verified_at")
        if isinstance(checked, datetime) and checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        expires = row.get("valid_until")
        if isinstance(expires, datetime):
            expires = expires.date()
        weekly = row.get("weekly_hours")
        if not (_official_url(row.get("source_url"))
                and isinstance(checked, datetime)
                and now - timedelta(days=MAX_RECORD_AGE_DAYS) <= checked <= now
                and isinstance(expires, date) and expires >= selected
                and isinstance(weekly, list) and len(weekly) <= 7
                and all(isinstance(x, str) and 0 < len(x) <= 200 for x in weekly)):
            updated.append(c)
            continue
        updates = {}
        if weekly:
            updates.update(
                published_weekly_hours=weekly,
                hours_source="official_website",
                hours_source_url=row["source_url"],
                hours_checked_at=checked.isoformat(),
            )
        notices = row.get("date_notices")
        if isinstance(notices, dict):
            notice = notices.get(selected.isoformat())
            if isinstance(notice, str) and 0 < len(notice) <= 500:
                updates.update(hours_date_notice=notice,
                               hours_source_url=row["source_url"],
                               hours_source="official_website",
                               hours_checked_at=checked.isoformat())
        updated.append(c.model_copy(update=updates) if updates else c)
    return updated


async def enrich_official_hours(candidates, visit_date=None):
    """Optional, fail-open Supabase query. Missing table requires no migration."""
    if os.getenv("OFFICIAL_HOURS_PROVIDER", "off").lower() != "postgres" or not candidates:
        return candidates, None
    try:
        rows = await asyncio.to_thread(_lookup, candidates)
        return apply_official_hours(candidates, rows, visit_date), None
    except Exception as exc:
        logger.warning("Official hours unavailable (%s)", type(exc).__name__)
        return candidates, "Official-source hours temporarily unavailable; unverified values remain unknown."
