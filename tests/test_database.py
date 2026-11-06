"""Regression tests for the curated activity query and response fields.

The city query must select every field later accessed by the row mapper,
including source_url (previously missing, causing a hidden KeyError/503).
"""
import sys
from types import ModuleType, SimpleNamespace

from app.database import _fetch
from app.models import RecommendationRequest


def test_city_query_selects_source_url(monkeypatch):
    rows = [{
        "source_id": "town_canmore_curated",
        "activity_id": "elevation_place",
        "name": "Elevation Place",
        "address": "700 Railway Ave, Canmore, AB",
        "latitude": 51.09,
        "longitude": -115.36,
        "website_url": None,
        "source_url": "https://www.canmore.ca/your-community/recreation",
        "activity_type": "indoor",
        "categories": ["recreation"],
        "price_category": "any",
        "min_age": None,
        "max_age": None,
        "google_place_id": None,
    }]
    class Cursor:
        def __init__(self):
            self.statement = ""
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, params=None):
            self.statement = sql
            if params is not None:
                assert "a.source_url" in sql
                assert params == ("AB", "Canmore")
        def fetchone(self): return {"linked": False}
        def fetchall(self): return rows

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return Cursor()

    fake_psycopg = ModuleType("psycopg")
    fake_psycopg.connect = lambda *args, **kwargs: Connection()
    fake_rows = ModuleType("psycopg.rows")
    fake_rows.dict_row = object()
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.rows", fake_rows)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test-placeholder")

    activities = _fetch(RecommendationRequest(city="Canmore", children_ages=[2]))
    assert len(activities) == 1
    assert activities[0].official_source_url == rows[0]["source_url"]
    assert activities[0].name == "Elevation Place"
