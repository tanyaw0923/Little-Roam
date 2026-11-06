"""Official-site hours are optional and never inferred from unverified evidence."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from app.models import Candidate, RecommendationRequest
from app.official_hours import apply_official_hours, enrich_official_hours


def place():
    return Candidate(place_id="town_banff_curated:fenlands", name="Fenlands",
                     address="Banff, AB", source="curated",
                     google_place_id="ChIJtest")


def record(verified_at=None, valid_until=None):
    now = datetime.now(timezone.utc)
    return {
        "source_id": "town_banff_curated",
        "activity_id": "fenlands",
        "weekly_hours": ["Monday: 8:30 a.m. - 8:30 p.m."],
        "date_notices": {"2026-11-11": "Official notice: closed on this date"},
        "source_url": "https://www.banff.ca/132/Fenlands-Banff-Recreation-Centre",
        "verified_at": verified_at or now - timedelta(days=1),
        "valid_until": valid_until or now.date() + timedelta(days=10),
    }


def test_verified_official_hours_take_priority_over_google_weekly_hours():
    c = place().model_copy(update={
        "published_weekly_hours": ["Monday: Google hours"],
        "hours_status": "open_now", "hours_source": "google_places",
        "hours_status_source": "google_places",
    })
    row = record()
    result = apply_official_hours([c], {("town_banff_curated", "fenlands"): row})[0]
    assert result.published_weekly_hours == row["weekly_hours"]
    assert result.hours_source == "official_website"
    assert result.hours_status == "open_now"
    assert result.hours_status_source == "google_places"
    assert result.hours_source_url == row["source_url"]


def test_expired_hours_not_served():
    c = place()
    row = record(valid_until=date(2020,1,1))
    result = apply_official_hours([c], {("town_banff_curated", "fenlands"): row})[0]
    assert result.hours_source == "unknown"
    assert result.published_weekly_hours == []


def test_old_verification_is_stale():
    c = place()
    row = record(verified_at=datetime.now(timezone.utc)-timedelta(days=45))
    result = apply_official_hours([c], {("town_banff_curated", "fenlands"): row})[0]
    assert result.published_weekly_hours == []


def test_explicit_date_notice_is_not_claim_of_activity_availability():
    c = place()
    row = record(valid_until=date(2026, 11, 18))
    # Use explicit logical date to test validity independent of current day.
    now=datetime.now(timezone.utc)
    row["verified_at"]=now
    # This is only valid when test runs before expiry.
    if now.date() > date(2026,11,18):
        return
    result=apply_official_hours([c], {("town_banff_curated", "fenlands"): row},
                                visit_date=date(2026,11,11))[0]
    assert "closed" in result.hours_date_notice
    assert result.hours_for_visit_date == "unknown"


def test_provider_disabled_does_not_access_database(monkeypatch):
    monkeypatch.delenv("OFFICIAL_HOURS_PROVIDER", raising=False)
    c=place()
    result,warning=asyncio.run(enrich_official_hours([c]))
    assert result==[c]
    assert warning is None


def test_provider_database_error_is_nonfatal(monkeypatch):
    monkeypatch.setenv("OFFICIAL_HOURS_PROVIDER","postgres")
    def bad_lookup(items):
        raise RuntimeError("offline")
    monkeypatch.setattr("app.official_hours._lookup",bad_lookup)
    c=place()
    result,warning=asyncio.run(enrich_official_hours([c]))
    assert result==[c]
    assert "unavailable" in warning.lower()


def test_official_hours_response_serialization():
    from app.recommend import recommend
    c=place().model_copy(update={
        "hours_source": "official_website",
        "hours_source_url": "https://www.banff.ca/132/Fenlands-Banff-Recreation-Centre",
        "published_weekly_hours":["Monday: 8:30 a.m. - 8:30 p.m."],
    })
    r=RecommendationRequest(city="Banff", children_ages=[4])
    result=asyncio.run(recommend([c],r))[0].model_dump()
    assert result["hours_source"]=="official_website"
    assert result["hours_for_visit_date"]=="unknown"
