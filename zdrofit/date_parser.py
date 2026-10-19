import datetime
from zoneinfo import ZoneInfo
from dateutil import parser
import re

# Zdrofit schedules are in Polish local time, regardless of this machine's timezone
CLUB_TZ = ZoneInfo("Europe/Warsaw")


def now_local() -> datetime.datetime:
    """Current time as a timezone-aware datetime in the club's timezone."""
    return datetime.datetime.now(CLUB_TZ)


POLISH_ENGLISH_WEEKDAYS = {
    # 0 = Monday, ..., 6 = Sunday
    'monday': 0, 'mondays': 0, 'poniedzialek': 0, 'poniedziałek': 0, 'poniedzialki': 0, 'poniedziałki': 0, 'pn': 0,
    'tuesday': 1, 'tuesdays': 1, 'wtorek': 1, 'wtorki': 1, 'wt': 1,
    'wednesday': 2, 'wednesdays': 2, 'sroda': 2, 'środa': 2, 'srody': 2, 'środy': 2, 'sr': 2, 'śr': 2,
    'thursday': 3, 'thursdays': 3, 'czwartek': 3, 'czwartki': 3, 'czw': 3,
    'friday': 4, 'fridays': 4, 'piatek': 4, 'piątek': 4, 'piatki': 4, 'piątki': 4, 'pt': 4,
    'saturday': 5, 'saturdays': 5, 'sobota': 5, 'soboty': 5, 'sob': 5, 'sb': 5,
    'sunday': 6, 'sundays': 6, 'niedziela': 6, 'niedziele': 6, 'nd': 6, 'niedz': 6,
}

def parse_weekday(val) -> int | None:
    """Parse weekday name or int into 0 (Mon) to 6 (Sun)."""
    if isinstance(val, int) and 0 <= val <= 6:
        return val
    if not val:
        return None
    clean = str(val).lower().strip()
    return POLISH_ENGLISH_WEEKDAYS.get(clean)

def parse_target_date(date_str: str) -> datetime.date:
    """
    Parse a user-provided date string into a datetime.date object.
    Supports ISO formats (YYYY-MM-DD), relative words (today, tomorrow),
    and weekday names in English and Polish (e.g. 'next Sunday', 'niedziela').
    """
    if not date_str:
        raise ValueError("Empty date string provided")

    now = now_local()
    clean = date_str.lower().strip()

    if clean in ('today', 'dzisiaj', 'dzis', 'dziś'):
        return now.date()
    if clean in ('tomorrow', 'jutro'):
        return (now + datetime.timedelta(days=1)).date()

    is_next = any(kw in clean for kw in ('next', 'kolejn', 'przyszł', 'przyszl'))

    for name, target_weekday in POLISH_ENGLISH_WEEKDAYS.items():
        # Match whole words or prefixes
        pattern = rf'\b{re.escape(name)}\b'
        if re.search(pattern, clean) or clean == name or clean == f"next {name}" or clean == f"next-{name}":
            days_ahead = (target_weekday - now.weekday()) % 7
            if is_next:
                days_ahead = days_ahead if days_ahead > 0 else 7
            elif days_ahead == 0:
                # If target weekday is today, assume next occurrence unless explicit
                days_ahead = 7
            return (now + datetime.timedelta(days=days_ahead)).date()

    # Try standard dateutil parser
    try:
        parsed = parser.parse(date_str, fuzzy=True)
        return parsed.date()
    except Exception as e:
        raise ValueError(f"Could not parse date '{date_str}': {e}")
