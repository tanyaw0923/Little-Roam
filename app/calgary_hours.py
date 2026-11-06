"""Parser for official City of Calgary recreation facility 'Hours of operation' pages.

Extracts the weekday/facility-hours table, NOT 'free public skate' programme
times or live rink status. Extracted data is only a review candidate.
"""
import re
from datetime import datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from .visit_hours import WEEKDAYS

ABBREVIATIONS = {d[:3].lower(): d for d in WEEKDAYS}
SEASON = re.compile(
    r"(Prime season|Year.round)\s*(?:\(([^)]{1,80})\))?", re.IGNORECASE
)
MONTH_NAMES = ("January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December")
MONTHS = {x.lower(): x[:3] for x in MONTH_NAMES}
CLOCK = re.compile(
    r"\b(?:1[0-2]|0?[1-9])(?::[0-5]\d)?\s*(?:a\.?m\.?|p\.?m\.?)\b",
    re.IGNORECASE,
)
WHITESPACE = re.compile(r"\s+")


def clean(text):
    return WHITESPACE.sub(" ", text.replace("\xa0", " ")).strip()


class CalgaryPage(HTMLParser):
    """Capture headings and table cells from the server-rendered Calgary HTML."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.heading = None
        self.heading_data = []
        self.headings = []
        self.title = None
        self.in_title = False
        self.title_data = []
        self.table = None
        self.tables = []
        self.row = None
        self.cell = None
        self.cell_parts = []
        self.capture = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "title":
            self.in_title = True
            self.title_data = []
        if tag in {"h1", "h2", "h3", "h4"}:
            self.heading = tag
            self.heading_data = []
        if tag == "table":
            self.table = {"headings": list(self.headings), "rows": []}
        if tag == "tr" and self.table is not None:
            self.row = []
        if tag in {"td", "th"} and self.row is not None:
            self.cell = tag
            self.cell_parts = []
        if tag == "br" and self.cell is not None:
            self.cell_parts.append(" ")

    def handle_data(self, data):
        if self.in_title:
            self.title_data.append(data)
        if self.heading is not None:
            self.heading_data.append(data)
        if self.cell is not None:
            self.cell_parts.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title" and self.in_title:
            self.title = clean("".join(self.title_data))
            self.in_title = False
        if tag == self.heading and self.heading is not None:
            self.headings.append((self.heading, clean("".join(self.heading_data))))
            self.heading = None
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append(clean("".join(self.cell_parts)))
            self.cell = None
        if tag == "tr" and self.row is not None:
            if self.row:
                self.table["rows"].append(self.row)
            self.row = None
        if tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def _season_suffix(headings):
    """Convert unambiguous calendar month bounds to the existing season format."""
    for _, h in reversed(headings):
        match = SEASON.search(h)
        if match:
            if match.group(1).casefold().replace("-", "") == "yearround":
                return ""
            names = re.split(r"\s+to\s+", (match.group(2) or "").strip(), flags=re.I)
            if len(names) != 2:
                return None
            a, b = (MONTHS.get(x.strip().lower()) for x in names)
            if not a or not b:
                return None
            # Month ranges only, not proof of opening on special holiday dates.
            ending = "28" if b == "Feb" else "30" if b in {"Apr", "Jun", "Sep", "Nov"} else "31"
            return f" ({a} 1 - {b} {ending})"
        if h.casefold() == "hours of operation":
            break
    return None


def _time_value(value):
    value = clean(re.sub(r"^Location\s*", "", value, flags=re.I))
    if re.fullmatch(r"closed", value, flags=re.I):
        return "Closed"
    if re.fullmatch(r"open\s+24\s+hours", value, flags=re.I):
        return "Open 24 hours"
    times = CLOCK.findall(value)
    if len(times) == 2 and re.search(r"\s[-–]\s", value):
        return value if len(value) <= 90 else None
    return None


def parse_calgary_facility_hours(html, venue_name):
    """Return candidate weekly schedule, never verified hours.

    Requires an exact named facility page, the specific hours table, a
    recognizable season/year-round heading and at least 5 explicit weekdays.
    Missing weekdays are NOT assumed to share today's hours.
    """
    parser = CalgaryPage()
    parser.feed(html)
    from .hours_discovery import normalize_name
    name = normalize_name(venue_name)
    # Page title is required; links to generic City schedules must not match.
    if not parser.title or name not in normalize_name(parser.title):
        return []
    possibilities = []
    for table in parser.tables:
        headings = table["headings"]
        names = [t.casefold() for _, t in headings]
        if not any("hours of operation" in x for x in names):
            continue
        # Don't accidentally scrape a different section's table.
        if any(x.startswith("special hours") for x in names[-2:]):
            continue
        suffix = _season_suffix(headings)
        if suffix is None:
            continue
        rows = table["rows"]
        if not rows or not any(len(row) >= 2 and "facility hours" in row[1].casefold()
                               for row in rows[:3]):
            continue
        found = {}
        conflict = False
        for row in rows:
            if len(row) < 2:
                continue
            label = re.sub(r"^Day:\s*", "", row[0], flags=re.I).strip()
            day = ABBREVIATIONS.get(label[:3].casefold()) if len(label) == 3 else next(
                (x for x in WEEKDAYS if label.casefold() == x.casefold()), None)
            # Dynamic 'Today' can be stale in cached HTML and is not authoritative.
            if not day:
                continue
            hours = _time_value(row[1])
            if not hours:
                continue
            line = f"{day}: {hours}{suffix}"
            if day in found and found[day] != line:
                conflict = True
            found[day] = line
        if not conflict and len(found) >= 5:
            possibilities.append(tuple(found[d] for d in WEEKDAYS if d in found))
    return list(possibilities[0]) if len(set(possibilities)) == 1 else []
