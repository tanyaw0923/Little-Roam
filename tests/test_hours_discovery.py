"""Official hours discovery is intentionally a review queue, not auto-publication."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.hours_discovery import (
    extract_structured_hours, safe_official_url, discover_row,
    format_spec, DEFAULT_HOSTS,
)

VENUE = "Civic Recreation Centre"
SCHEDULE = {
    "@context": "https://schema.org",
    "@type": "SportsActivityLocation",
    "name": VENUE,
    "openingHoursSpecification": [
        {"@type": "OpeningHoursSpecification",
         "dayOfWeek": ["https://schema.org/Monday", "https://schema.org/Tuesday"],
         "opens": "09:00", "closes": "17:00"},
        {"@type": "OpeningHoursSpecification",
         "dayOfWeek": "Friday", "opens": "10:00", "closes": "18:00"},
    ]
}


def page(data):
    return '<html><script type="application/ld+json">' + json.dumps(data) + '</script></html>'


def test_structured_named_venue_hours():
    assert extract_structured_hours(page(SCHEDULE), VENUE) == [
        "Monday: 09:00 - 17:00",
        "Tuesday: 09:00 - 17:00",
        "Friday: 10:00 - 18:00",
    ]


def test_wrong_venue_and_generic_site_hours_never_accepted():
    assert extract_structured_hours(page(SCHEDULE), "Another Centre") == []
    doc = {**SCHEDULE, "@type": "Organization"}
    assert extract_structured_hours(page(doc), VENUE) == []


def test_unstructured_text_not_accepted():
    assert extract_structured_hours("<html>Monday: 9am-5pm</html>", VENUE) == []


def test_conflicting_venue_specs_rejected():
    doc = {**SCHEDULE, "openingHoursSpecification": [
        {"dayOfWeek": "Friday", "opens": "09:00", "closes": "17:00"},
        {"dayOfWeek": "Friday", "opens": "10:00", "closes": "18:00"},
    ]}
    assert extract_structured_hours(page(doc), VENUE) == []


def test_malformed_times_do_not_get_published():
    assert format_spec({"dayOfWeek": "Monday", "opens": "9am", "closes": "17:00"}) == {}


@pytest.mark.parametrize("url", [
    "http://calgary.ca/recreation",
    "https://calgary.ca.evil.invalid/recreation",
    "https://127.0.0.1/recreation",
    "https://user:pass@calgary.ca/recreation",
    "https://calgary.ca:8443/recreation",
    "https://calgary.ca/file.pdf",
    "https://evil.invalid/venue",
])
def test_url_allowlist(url):
    assert not safe_official_url(url, DEFAULT_HOSTS)


def test_official_subdomain_allowed():
    assert safe_official_url("https://www.calgary.ca/venues/one", DEFAULT_HOSTS)


def test_discover_stages_only_not_approves(monkeypatch):
    from app import hours_discovery
    monkeypatch.setattr(hours_discovery, "fetch_official_page", lambda client, url, hosts: page(SCHEDULE))
    row = {"source_id": "calgary_recreation_facilities", "activity_id": "one",
           "name": VENUE, "website_url": "https://www.calgary.ca/venues/one",
           "source_url": "https://data.calgary.ca"}
    result = discover_row(None, row, DEFAULT_HOSTS)
    assert result["status"] == "pending_review"
    assert result["weekly_hours"][0] == "Monday: 09:00 - 17:00"
    assert "verified_at" not in result
    assert "valid_until" not in result


def test_unknown_host_is_not_fetched(monkeypatch):
    from app import hours_discovery
    monkeypatch.setattr(hours_discovery, "fetch_official_page",
                        lambda *args: pytest.fail("unsafe network request"))
    row = {"source_id": "x", "activity_id": "y", "name": VENUE,
           "website_url": "https://unapproved.example/venue",
           "source_url": "https://unapproved.example/"}
    assert discover_row(None, row, DEFAULT_HOSTS) is None
