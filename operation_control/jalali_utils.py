"""
Jalali helpers for server-side logic. Dates are stored as ordinary Gregorian
`DateField`s (like the rest of the project, with the Jalali datepicker handling
the browser side); this module converts only where the app needs Jalali
calendar logic: seasons, plan weeks, "same day next year" due dates, display.

No third-party dependency. The conversion uses the standard 33-year-cycle
arithmetic, valid for the current era (checked against known dates in tests).
"""
import datetime
import re

_LEAP_REMAINDERS = {1, 5, 9, 13, 17, 22, 26, 30}
_JDATE_RE = re.compile(r"^\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*$")
_G_DAYS_BEFORE_MONTH = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


# ---------------------------------------------------------------- pure calendar maths
def is_leap(year: int) -> bool:
    return year % 33 in _LEAP_REMAINDERS


def days_in_month(year: int, month: int) -> int:
    if month <= 6:
        return 31
    if month <= 11:
        return 30
    return 30 if is_leap(year) else 29


def gregorian_to_jalali(gy: int, gm: int, gd: int):
    if gy > 1600:
        jy, gy = 979, gy - 1600
    else:
        jy, gy = 0, gy - 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
            - 80 + gd + _G_DAYS_BEFORE_MONTH[gm - 1])
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def jalali_to_gregorian(jy: int, jm: int, jd: int):
    if jy > 979:
        gy, jy = 1600, jy - 979
    else:
        gy = 621
    days = (365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + 78 + jd
            + ((jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186))
    gy += 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    feb = 29 if (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0 else 28
    month_lengths = [0, 31, feb, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > month_lengths[gm]:
        gd -= month_lengths[gm]
        gm += 1
    return gy, gm, gd


def add_months_ymd(year: int, month: int, day: int, months: int):
    """Same day-of-month, `months` later (Jalali); the day is clamped to the month length."""
    total = year * 12 + (month - 1) + months
    y, m0 = divmod(total, 12)
    m = m0 + 1
    return y, m, min(day, days_in_month(y, m))


def season_of_month(month: int) -> int:
    """1=Spring (Farvardin-Khordad) ... 4=Winter (Dey-Esfand)."""
    return (month - 1) // 3 + 1


def plan_week_ymd(month: int, day: int, first_month: int = 2) -> int:
    """
    Inspection-plan 'week' index, identical to the Excel logic: 4 slots per
    Jalali month (days 1-7, 8-14, 15-21, 22+) counted from `first_month`.
    0 = before the plan starts.
    """
    if month < first_month:
        return 0
    slot = 1 if day <= 7 else 2 if day <= 14 else 3 if day <= 21 else 4
    return (month - first_month) * 4 + slot


def parse_jalali_str(value):
    """'1405/04/24' -> (1405, 4, 24), or None if it is not a valid Jalali date."""
    if value is None:
        return None
    m = _JDATE_RE.match(str(value))
    if not m:
        return None
    y, mo, d = (int(g) for g in m.groups())
    if not (1200 <= y <= 1600 and 1 <= mo <= 12 and 1 <= d <= days_in_month(y, mo)):
        return None
    return y, mo, d


# ---------------------------------------------------------------- date-object helpers
def to_jalali(d):
    """datetime.date / datetime -> (jy, jm, jd)."""
    return gregorian_to_jalali(d.year, d.month, d.day)


def from_jalali(jy: int, jm: int, jd: int) -> datetime.date:
    return datetime.date(*jalali_to_gregorian(jy, jm, jd))


def today() -> datetime.date:
    from django.utils import timezone
    return timezone.localdate()


def jalali_today():
    return to_jalali(today())


def add_months(d, months: int):
    """Jalali-aware month arithmetic on a Gregorian date (None-safe)."""
    if d is None:
        return None
    return from_jalali(*add_months_ymd(*to_jalali(d), months))


def add_days(d, days: int):
    return d + datetime.timedelta(days=days)


def days_between(later, earlier) -> int:
    return (later - earlier).days


def season_of_date(d) -> int:
    return season_of_month(to_jalali(d)[1])


def fmt(d) -> str:
    """Always Jalali: 1405/04/24."""
    if not d:
        return ""
    return "%04d/%02d/%02d" % to_jalali(d)


def display(d) -> str:
    """Jalali when the UI language is Persian, ISO (YYYY-MM-DD) otherwise - same rule as localization.js."""
    if not d:
        return ""
    from django.utils.translation import get_language
    if (get_language() or "").startswith("fa"):
        return fmt(d)
    return d.strftime("%Y-%m-%d")
