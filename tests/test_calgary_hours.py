"""City of Calgary official venue-hours page parser regression tests."""
from app.calgary_hours import parse_calgary_facility_hours
from app.hours_discovery import candidate_hours_urls, discover_row

def html_page(name="Rose Kohn Arena", season="Prime season (October to March)", closed="Wed"):
    days=("Fri","Sat","Sun","Mon","Tue","Wed","Thu")
    entries="".join(
        "<tr><td>Day: "+d+"</td><td>Location "+(
            "Closed" if d==closed else "6:30 a.m. - 11:30 p.m.")+"</td></tr>"
        for d in days)
    return (
        "<html><head><title>Facility information and hours - "+name+"</title></head><body>"
        "<h1>Facility information and hours - "+name+"</h1>"
        "<h2>Free public skate</h2><p>From 1 - 2:15 p.m. on holidays</p>"
        "<h2>Hours of operation</h2><h3>"+season+"</h3>"
        "<p>Requests outside these hours will be considered.</p>"
        "<table><thead><tr><th>Day</th><th>Facility hours</th></tr></thead>"
        "<tbody><tr><td>Day: Today</td><td>Location 6:30 a.m. - 11:30 p.m.</td></tr>"
        + entries + "</tbody></table>"
        "<h3>Special hours and facility closure dates</h3>"
        "<ul><li>Dec 25: Closed</li></ul></body></html>"
    )


def test_rose_kohn_table_extracts_weekdays_and_winter_season():
    actual=parse_calgary_facility_hours(html_page(), "Rose Kohn Arena")
    assert len(actual)==7
    assert actual[4]=="Friday: 6:30 a.m. - 11:30 p.m. (Oct 1 - Mar 31)"
    assert actual[2]=="Wednesday: Closed (Oct 1 - Mar 31)"
    assert all("free public skate" not in x.lower() for x in actual)


def test_year_round_days():
    lines=parse_calgary_facility_hours(html_page(season="Year-round",closed="Sat"),
                                        "Rose Kohn Arena")
    assert len(lines)==7
    assert lines[5]=="Saturday: Closed"
    assert all("(Oct" not in x for x in lines)


def test_wrong_facility_page_rejected():
    assert parse_calgary_facility_hours(html_page("Other Arena"), "Rose Kohn Arena")==[]


def test_missing_season_label_is_not_assumed_year_round():
    assert parse_calgary_facility_hours(html_page(season="Hours may vary"),"Rose Kohn Arena")==[]


def test_same_name_without_hours_table_is_empty():
    content=("<html><head><title>Facility information and hours - Rose Kohn Arena"
             "</title></head><body><h2>Free public skate</h2>"
             "<table><tr><th>Day</th><th>Facility hours</th></tr>"
             "<tr><td>Day: Fri</td><td>1 p.m. - 2 p.m.</td></tr>"
             "</table></body></html>")
    assert parse_calgary_facility_hours(content,"Rose Kohn Arena")==[]


def test_arena_url_candidate_from_calgary_source_only():
    row={"source_id":"calgary_recreation_facilities","name":"Rose Kohn Arena",
         "website_url":None,"source_url":"https://data.calgary.ca/about"}
    candidates=candidate_hours_urls(row)
    assert candidates[0]=="https://www.calgary.ca/rec-locations/arenas/rose-kohn-hours.html"
    assert "https://data.calgary.ca/about" in candidates
    row["source_id"]="different_source"
    assert all("rose-kohn-hours" not in (u or "") for u in candidate_hours_urls(row))


def test_discover_row_extracts_calgary_table_for_review(monkeypatch):
    from app import hours_discovery
    def mock_fetch(client,url,hosts):
        assert url.endswith("/rose-kohn-hours.html")
        return html_page()
    monkeypatch.setattr(hours_discovery,"fetch_official_page",mock_fetch)
    row={"source_id":"calgary_recreation_facilities","activity_id":"test-rose",
         "name":"Rose Kohn Arena", "website_url":None,
         "source_url":"https://data.calgary.ca/about"}
    output=discover_row(None,row,("calgary.ca","data.calgary.ca"))
    assert output["status"]=="pending_review"
    assert len(output["weekly_hours"])==7
    assert "verified_at" not in output
