"""Opt-in, operator-controlled official-hours discovery and human review.

Run as: python -m app.hours_discovery discover [--apply] [--limit 20]
        python -m app.hours_discovery pending
        python -m app.hours_discovery approve SOURCE_ID ACTIVITY_ID --confirm

Only structured schema.org venue schedules are extracted from approved
independently sourced website URLs. No Google content or arbitrary web search
results are persisted. Nothing is published until an operator approves.
"""
import argparse
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import ipaddress
import json
import os
import re
import socket
from urllib.parse import urlparse

import httpx

from .visit_hours import WEEKDAYS

MAX_PAGE_BYTES = 800_000
MAX_TARGETS = 30
DEFAULT_HOSTS = ("calgary.ca", "canmore.ca", "banff.ca", "parks.canada.ca")


def allowed_hosts():
    supplied = os.getenv("OFFICIAL_HOURS_ALLOWED_HOSTS", "")
    return tuple(x.strip().lower() for x in supplied.split(",") if x.strip()) or DEFAULT_HOSTS


def safe_official_url(value, hosts=None):
    """HTTPS, explicit official-host allowlist, no ports/credentials/IP addresses."""
    if not isinstance(value, str) or len(value) > 1500:
        return False
    try:
        u = urlparse(value)
        host = (u.hostname or "").lower().rstrip(".")
        approved = hosts if hosts is not None else allowed_hosts()
        return (u.scheme == "https" and u.port is None and u.username is None
                and u.password is None and not u.fragment
                and bool(host) and not host.replace(".", "").isdigit()
                and any(host == h or host.endswith("." + h) for h in approved)
                and not u.path.lower().endswith((".pdf", ".zip", ".jpg", ".png")))
    except ValueError:
        return False


def _public_dns(host):
    """Fail closed if a whitelisted host resolves to a private/reserved IP."""
    try:
        addresses = {x[4][0] for x in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
        return bool(addresses) and all(ipaddress.ip_address(a).is_global for a in addresses)
    except (OSError, ValueError):
        return False


class StructuredDataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.data = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script":
            attributes = dict(attrs)
            if "ld+json" in attributes.get("type", "").lower():
                self.inside = True
                self.data = []

    def handle_data(self, data):
        if self.inside:
            self.data.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.inside:
            self.scripts.append("".join(self.data))
            self.data = []
            self.inside = False


def normalize_name(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def walk_nodes(value):
    """Walk schema.org JSON-LD nested graphs without trusting arbitrary page text."""
    if isinstance(value, list):
        for x in value:
            yield from walk_nodes(x)
    elif isinstance(value, dict):
        yield value
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in value:
                yield from walk_nodes(value[key])


def weekday(value):
    word = str(value).rstrip("/").rsplit("/", 1)[-1].capitalize()
    return word if word in WEEKDAYS else None


def format_spec(spec):
    if not isinstance(spec, dict):
        return {}
    days = spec.get("dayOfWeek") or []
    if isinstance(days, str):
        days = [days]
    if not isinstance(days, list):
        return {}
    opens, closes = spec.get("opens"), spec.get("closes")
    if not (isinstance(opens, str) and isinstance(closes, str)):
        return {}
    # Strict 24h-clock schema.org times; reject malformed times.
    pattern = r"^([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$"
    if not (re.fullmatch(pattern, opens) and re.fullmatch(pattern, closes)):
        return {}
    start, end = opens[:5], closes[:5]
    label = "Open 24 hours" if start == "00:00" and end == "23:59" else f"{start} - {end}"
    result = {}
    for day in days:
        d = weekday(day)
        if d and d not in result:
            result[d] = f"{d}: {label}"
    return result


def extract_structured_hours(html, venue_name):
    """Use only JSON-LD with exact normalized venue name and recognized schema type.

    Multiple conflicting specifications are rejected; no generic sitewide hours.
    """
    parser = StructuredDataParser()
    parser.feed(html)
    results = []
    accepted_types = {"Place", "LocalBusiness", "CivicStructure", "SportsActivityLocation",
                      "Museum", "TouristAttraction", "GovernmentBuilding", "HealthClub"}
    for raw in parser.scripts:
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            continue
        for node in walk_nodes(parsed):
            types = node.get("@type", [])
            if isinstance(types, str):
                types = [types]
            normalized_types = {str(t).rsplit("/", 1)[-1] for t in types}
            if not normalized_types.intersection(accepted_types):
                continue
            if normalize_name(node.get("name", "")) != normalize_name(venue_name):
                continue
            specs = node.get("openingHoursSpecification")
            if isinstance(specs, dict):
                specs = [specs]
            if not isinstance(specs, list):
                continue
            schedule = {}
            conflict = False
            for spec in specs:
                for day, line in format_spec(spec).items():
                    if day in schedule and schedule[day] != line:
                        conflict = True
                    schedule[day] = line
            if schedule and not conflict:
                results.append(tuple(schedule[d] for d in WEEKDAYS if d in schedule))
    unique = set(results)
    return list(next(iter(unique))) if len(unique) == 1 else []


def find_missing_indoor(conn, limit):
    """Find indoor venues with no fresh independent official schedule."""
    from psycopg.rows import dict_row
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT a.source_id,a.activity_id,a.name,a.website_url,a.source_url
            FROM public.activities a
            LEFT JOIN public.activity_official_hours h
              ON a.source_id=h.source_id AND a.activity_id=h.activity_id
            WHERE a.active=TRUE AND a.activity_type='indoor'
              AND (h.source_id IS NULL OR h.valid_until<CURRENT_DATE
                   OR h.verified_at<NOW()-INTERVAL '30 days'
                   OR cardinality(h.weekly_hours)=0)
            ORDER BY a.city,a.name
            LIMIT %s
        """, (min(max(limit, 1), MAX_TARGETS),))
        return cur.fetchall()


def fetch_official_page(client, url, hosts):
    if not safe_official_url(url, hosts):
        raise ValueError("Host not approved")
    host = urlparse(url).hostname
    if not _public_dns(host):
        raise ValueError("DNS failed public-IP safety check")
    # No redirects; never follow an untrusted Location.
    with client.stream("GET", url, follow_redirects=False,
                       headers={"Accept": "text/html"}) as resp:
        resp.raise_for_status()
        if resp.status_code != 200 or "text/html" not in resp.headers.get("content-type", "").lower():
            raise ValueError("Not an HTML response")
        if int(resp.headers.get("content-length") or 0) > MAX_PAGE_BYTES:
            raise ValueError("Page too large")
        chunks, size = [], 0
        for part in resp.iter_bytes():
            size += len(part)
            if size > MAX_PAGE_BYTES:
                raise ValueError("Page exceeded size limit")
            chunks.append(part)
        return b"".join(chunks).decode("utf-8", errors="replace")


def discover_row(client, row, hosts):
    """At most one approved URL per activity; no crawling or guessing."""
    urls = (row.get("website_url"), row.get("source_url"))
    url = next((u for u in urls if safe_official_url(u, hosts)), None)
    if not url:
        return None   # Unapproved URLs are not fetched or queued.
    try:
        html = fetch_official_page(client, url, hosts)
        weekly = extract_structured_hours(html, row["name"])
        status = "pending_review" if weekly else "no_structured_hours"
    except (httpx.HTTPError, ValueError, OSError):
        weekly, status = [], "fetch_failed"
    return {**row, "source_url": url, "weekly_hours": weekly, "status": status}


def save_discoveries(conn, items):
    """Upsert *queue only*: never touch already approved official hours."""
    with conn.cursor() as cur:
        for item in items:
            cur.execute("""
                INSERT INTO public.activity_hours_review_queue
                  (source_id,activity_id,discovered_hours,source_url,discovery_status,discovered_at)
                VALUES (%s,%s,%s,%s,%s,NOW())
                ON CONFLICT (source_id,activity_id) DO UPDATE SET
                  discovered_hours=EXCLUDED.discovered_hours,
                  source_url=EXCLUDED.source_url,
                  discovery_status=EXCLUDED.discovery_status,
                  discovered_at=EXCLUDED.discovered_at
            """, (item["source_id"], item["activity_id"], item["weekly_hours"],
                  item["source_url"], item["status"]))
    conn.commit()


def approve(conn, source_id, activity_id, reviewer, days=14):
    """Promotion requires a person to inspect the actual official page."""
    from psycopg.rows import dict_row
    with conn.transaction():
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT discovered_hours,source_url,discovery_status,discovered_at
                FROM public.activity_hours_review_queue
                WHERE source_id=%s AND activity_id=%s FOR UPDATE
            """, (source_id, activity_id))
            row = cur.fetchone()
            if not row or row["discovery_status"] != "pending_review" or not row["discovered_hours"]:
                raise ValueError("No pending structured hours to approve")
            if not safe_official_url(row["source_url"]):
                raise ValueError("Source URL no longer approved")
            if row["discovered_at"] is None or (datetime.now(timezone.utc) - row["discovered_at"]).days > 7:
                raise ValueError("Discovery older than 7 days; rediscover and re-review")
            cur.execute("""
                INSERT INTO public.activity_official_hours
                  (source_id,activity_id,weekly_hours,date_notices,source_url,
                   verified_at,valid_until,notes)
                VALUES (%s,%s,%s,'{}'::jsonb,%s,NOW(),%s,%s)
                ON CONFLICT(source_id,activity_id) DO UPDATE SET
                  weekly_hours=EXCLUDED.weekly_hours,
                  date_notices=EXCLUDED.date_notices,
                  source_url=EXCLUDED.source_url,
                  verified_at=EXCLUDED.verified_at,
                  valid_until=EXCLUDED.valid_until,
                  notes=EXCLUDED.notes
            """, (source_id, activity_id, row["discovered_hours"], row["source_url"],
                  (datetime.now(timezone.utc) + timedelta(days=days)).date(),
                  f"Manually reviewed by {reviewer}; structured official-site schedule. "
                  "Holiday/seasonal exceptions require independent review."))
            cur.execute("""
                DELETE FROM public.activity_hours_review_queue
                WHERE source_id=%s AND activity_id=%s
            """, (source_id, activity_id))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Official indoor-hours discovery with human approval")
    sub = parser.add_subparsers(dest="action", required=True)
    d = sub.add_parser("discover")
    d.add_argument("--apply", action="store_true", help="Save proposals to review queue")
    d.add_argument("--limit", type=int, default=15)
    sub.add_parser("pending")
    a = sub.add_parser("approve")
    a.add_argument("source_id")
    a.add_argument("activity_id")
    a.add_argument("--reviewer", required=True)
    a.add_argument("--confirm", action="store_true",
                   help="Affirm you inspected the official page and checked any exceptions")
    args = parser.parse_args(argv)

    import psycopg
    url = os.getenv("DATABASE_URL")
    if not url:
        parser.error("DATABASE_URL is required")
    with psycopg.connect(url, connect_timeout=10) as conn:
        if args.action == "discover":
            rows = find_missing_indoor(conn, args.limit)
            with httpx.Client(timeout=12, follow_redirects=False, trust_env=False) as client:
                results = [result for row in rows
                           if (result := discover_row(client, row, allowed_hosts())) is not None]
            if args.apply:
                save_discoveries(conn, results)
            print(json.dumps({"dry_run": not args.apply, "candidates": len(rows),
                              "review_items": results}, indent=2, default=str))
        elif args.action == "pending":
            from psycopg.rows import dict_row
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                  SELECT q.source_id,q.activity_id,a.name,q.discovered_hours,
                         q.source_url,q.discovery_status,q.discovered_at
                  FROM public.activity_hours_review_queue q
                  JOIN public.activities a USING(source_id,activity_id)
                  ORDER BY q.discovery_status,q.discovered_at DESC LIMIT 100
                """)
                print(json.dumps(cur.fetchall(), default=str, indent=2))
        else:
            if not args.confirm or not args.reviewer.strip():
                parser.error("Approval requires --reviewer NAME and --confirm after inspection")
            approve(conn, args.source_id, args.activity_id, args.reviewer.strip())
            print(json.dumps({"approved": f"{args.source_id}:{args.activity_id}",
                              "reviewer": args.reviewer}))


if __name__ == "__main__":
    main()
