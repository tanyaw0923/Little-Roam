"""Visit-date schedule presentation; no Google API requests."""
import asyncio
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models import Candidate, RecommendationRequest
from app.recommend import recommend
from app.visit_hours import hours_for_weekday

WEEKLY = [
    "Monday: 11 a.m. - 5 p.m. (Oct 16 - May 14)",
    "Tuesday: Closed (Oct 16 - May 14)",
    "Wednesday: Closed (Oct 16 - May 14)",
    "Thursday: 11 a.m. - 5 p.m. (Oct 16 - May 14)",
    "Friday: 11 a.m. - 5 p.m. (Oct 16 - May 14)",
    "Saturday: 11 a.m. - 5 p.m. (Oct 16 - May 14)",
    "Sunday: 11 a.m. - 5 p.m. (Oct 16 - May 14)",
]


def test_friday_returns_only_friday():
    assert hours_for_weekday(WEEKLY, date(2026, 11, 6)) == [WEEKLY[4]]


def test_tuesday_returns_closed_for_selected_day():
    assert hours_for_weekday(WEEKLY, date(2026, 11, 10)) == [WEEKLY[1]]


def test_off_season_is_not_shown_as_current_hours():
    assert hours_for_weekday(WEEKLY, date(2027, 7, 2)) == []


def test_season_crosses_year_and_inclusive_endpoints():
    assert hours_for_weekday(WEEKLY, date(2027, 1, 1)) == [WEEKLY[4]]
    assert hours_for_weekday(WEEKLY, date(2027, 5, 14)) == [WEEKLY[4]]
    assert hours_for_weekday(WEEKLY, date(2027, 5, 15)) == []


def test_day_match_uses_label_not_array_position():
    data = ["Saturday: 8 AM - 2 PM", "Friday: 9 AM - 5 PM"]
    assert hours_for_weekday(data, date(2026, 11, 6)) == [data[1]]


def test_missing_or_unmatched_day_is_unknown_not_inferred():
    assert hours_for_weekday([], date(2026, 11, 6)) == []
    assert hours_for_weekday(["Monday: 9 AM - 5 PM"], date(2026, 11, 6)) == []


def test_recommendation_json_contains_only_selected_day(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    selected = datetime.now(ZoneInfo("America/Edmonton")).date() + timedelta(days=1)
    r = RecommendationRequest(city="Banff", children_ages=[4],
                              visit_date=selected)
    c = Candidate(
        place_id="parks_canada_curated:cave_and_basin",
        name="Cave and Basin National Historic Site",
        address="Banff, AB", source="curated",
        hours_source="official_website",
        published_weekly_hours=WEEKLY,
        hours_date_notice="Special closure: check venue notice",
    )
    results = asyncio.run(recommend([c], r))
    data = results[0].model_dump()
    matched = hours_for_weekday(WEEKLY, selected)
    assert data["published_weekly_hours"] == matched
    assert data["visit_day_hours"] == (matched[0] if matched else None)
    assert data["hours_date_notice"] == "Special closure: check venue notice"
    assert data["hours_schedule_verified"] is bool(matched)
    assert data["hours_for_visit_date"] == "unknown"


def test_missing_day_clears_verified_schedule_flag(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = RecommendationRequest(city="Banff", children_ages=[4],
                              visit_date=date(2026, 11, 6))
    c = Candidate(place_id="x", name="Example", address="Banff, AB",
                  source="curated", hours_source="official_website",
                  published_weekly_hours=["Monday: 8 AM - 5 PM"])
    data = asyncio.run(recommend([c], r))[0].model_dump()
    assert data["visit_day_hours"] is None
    assert data["published_weekly_hours"] == []
    assert data["hours_schedule_verified"] is False
