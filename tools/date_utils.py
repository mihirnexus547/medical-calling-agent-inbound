"""Date resolution helpers and calendar context generator."""

import calendar
import re
from datetime import date, datetime, timedelta

from langchain_core.tools import tool

from config import logger


def resolve_date_helper(expr: str):
    """
    Resolve relative date descriptions or date strings into a (datetime.date, weekday_name) tuple.
    Returns (None, None) if expression cannot be parsed.
    """
    if not expr:
        return None, None

    today = date.today()
    clean = str(expr).strip().lower()

    if clean == "today":
        return today, today.strftime("%A")
    if clean == "tomorrow":
        d = today + timedelta(days=1)
        return d, d.strftime("%A")
    if clean == "day after tomorrow":
        d = today + timedelta(days=2)
        return d, d.strftime("%A")

    m = re.match(r"in\s+(\d+)\s+days?", clean)
    if m:
        d = today + timedelta(days=int(m.group(1)))
        return d, d.strftime("%A")

    weekdays = {name.lower(): idx for idx, name in enumerate(calendar.day_name)}
    matched_weekday = None
    for name, idx in weekdays.items():
        if re.search(r"\b" + name + r"\b", clean):
            matched_weekday = idx
            break

    if matched_weekday is not None:
        today_weekday = today.weekday()
        days_ahead = (matched_weekday - today_weekday) % 7
        if days_ahead == 0:
            days_ahead = 7

        if "next" in clean:
            # If target weekday is still ahead this week (e.g. today is Thursday, asking for
            # Friday), 'next Friday' refers to the Friday of the *following* week (+7 days).
            if days_ahead < 7 and matched_weekday > today_weekday:
                days_ahead += 7

        d = today + timedelta(days=days_ahead)
        return d, d.strftime("%A")

    clean_date = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", clean)
    for fmt in [
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
        "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y",
        "%d %b", "%d %B", "%b %d", "%B %d",
    ]:
        try:
            parsed = datetime.strptime(clean_date, fmt).date()
            if parsed.year == 1900:
                parsed = parsed.replace(year=today.year)
            return parsed, parsed.strftime("%A")
        except ValueError:
            pass

    return None, None


def get_calendar_context() -> str:
    """Generate dynamic calendar context for the upcoming 14 days."""
    today = date.today()
    lines = [
        f"CALENDAR & DATE REFERENCE (Today is {today.strftime('%A, %Y-%m-%d')}):",
        "Upcoming 14-day calendar:",
    ]
    for i in range(15):
        d = today + timedelta(days=i)
        day_name = d.strftime("%A")
        qualifier = ""
        if i == 0:
            qualifier = " [Today]"
        elif i == 1:
            qualifier = f" [Tomorrow / This {day_name}]"
        elif i <= 6:
            qualifier = f" [This {day_name}]"
        elif i == 7:
            qualifier = " [Next week same day]"
        elif i <= 13:
            qualifier = f" [Next {day_name}]"
        lines.append(f"  - {d.strftime('%Y-%m-%d')}: {day_name}{qualifier}")
    lines.append(
        "CRITICAL INSTRUCTION: When the user mentions any relative date (e.g. 'next Friday', "
        "'tomorrow', 'this Monday', 'Oct 23'), ALWAYS check the calendar reference above or call "
        "the resolve_relative_date tool. Never hallucinate day-of-week mappings. "
        "For example, if today is Thursday Oct 15, tomorrow is Friday Oct 16, "
        "and 'next Friday' is Friday Oct 23."
    )
    return "\n".join(lines)


@tool
def resolve_relative_date(query: str) -> str:
    """Resolve any relative date expression (e.g. 'today', 'tomorrow', 'this friday',
    'next friday', 'next monday', or '23 oct 2026') to the exact YYYY-MM-DD date
    and corresponding weekday."""
    import time
    start_time = time.perf_counter()
    logger.info("Resolving relative date started: query=%s", query)

    resolved_date, day_name = resolve_date_helper(query)
    duration = time.perf_counter() - start_time

    if resolved_date:
        res = f"{resolved_date.isoformat()} ({day_name})"
        logger.info(
            "Resolving relative date completed: query=%s result=%s duration=%.3fs",
            query,
            res,
            duration,
        )
        return f"Date: {resolved_date.isoformat()} ({day_name})"

    logger.warning(
        "Resolving relative date could not parse: query=%s duration=%.3fs",
        query,
        duration,
    )
    return f"Could not parse date expression: '{query}'. Please provide a specific date like YYYY-MM-DD."
