"""Present only the published schedule for the selected visit weekday.

This is a filter, not a live availability check: special closures and specific
swimming/skating sessions are represented separately and never inferred.
"""
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = {name.lower(): i for i, name in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}
SEASON_PATTERN = re.compile(
    r"\(([A-Za-z]{3})\s+(\d{1,2})\s*[-–]\s*([A-Za-z]{3})\s+(\d{1,2})\)",
    re.IGNORECASE,
)


def _season_applies(hours: str, selected: date) -> bool:
    """When a known month/day seasonal qualifier exists, don't show it out of season."""
    match = SEASON_PATTERN.search(hours)
    if match is None:
        return True
    a_month = MONTHS.get(match.group(1).lower())
    b_month = MONTHS.get(match.group(3).lower())
    if a_month is None or b_month is None:
        return False
    start, end = (a_month, int(match.group(2))), (b_month, int(match.group(4)))
    current = (selected.month, selected.day)
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def hours_for_weekday(weekly: list[str], visit_date: date) -> list[str]:
    """Only return the matching day's complete source line; never assume array order."""
    day = WEEKDAYS[visit_date.weekday()].casefold()
    matches = []
    for item in weekly:
        if not isinstance(item, str):
            continue
        label, delimiter, _ = item.partition(":")
        if delimiter and label.strip().casefold() == day and _season_applies(item, visit_date):
            matches.append(item)
    return matches[:1]


def chosen_visit_date(value: date | None) -> date:
    return value or datetime.now(ZoneInfo("America/Edmonton")).date()
