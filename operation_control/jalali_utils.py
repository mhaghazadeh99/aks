"""
Small Jalali helpers. The arithmetic lives in pure (year, month, day) functions
so it can be tested without Django/jdatetime; the thin wrappers below work on
jdatetime.date objects (what django-jalali's jDateField returns).
"""
import re

_LEAP_REMAINDERS = {1, 5, 9, 13, 17, 22, 26, 30}  # 33-year rule, same as jdatetime
_JDATE_RE = re.compile(r"^\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*$")


def is_leap(year: int) -> bool:
    return year % 33 in _LEAP_REMAINDERS


def days_in_month(year: int, month: int) -> int:
    if month <= 6:
        return 31
    if month <= 11:
        return 30
    return 30 if is_leap(year) else 29


def add_months_ymd(year: int, month: int, day: int, months: int):
    """Same day-of-month, `months` later; day is clamped to the month length."""
    total = year * 12 + (month - 1) + months
    y, m0 = divmod(total, 12)
    m = m0 + 1
    return y, m, min(day, days_in_month(y, m))


def season_of_month(month: int) -> int:
    """1=Spring (Farvardin-Khordad) ... 4=Winter (Dey-Esfand)."""
    return (month - 1) // 3 + 1


def plan_week_ymd(month: int, day: int, first_month: int = 2) -> int:
    """
    Inspection-plan 'week' index, identical to the Excel logic:
    4 slots per month (days 1-7, 8-14, 15-21, 22+), counted from `first_month`.
    Returns 0 when the date is before the plan starts.
    """
    if month < first_month:
        return 0
    slot = 1 if day <= 7 else 2 if day <= 14 else 3 if day <= 21 else 4
    return (month - first_month) * 4 + slot


def parse_jalali_str(value):
    """'1405/04/24' -> (1405, 4, 24) or None if it is not a valid Jalali date."""
    if value is None:
        return None
    m = _JDATE_RE.match(str(value))
    if not m:
        return None
    y, mo, d = (int(g) for g in m.groups())
    if not (1200 <= y <= 1600 and 1 <= mo <= 12 and 1 <= d <= days_in_month(y, mo)):
        return None
    return y, mo, d


# ---- jdatetime wrappers --------------------------------------------------
def today():
    import jdatetime
    return jdatetime.date.today()


def from_str(value):
    import jdatetime
    ymd = parse_jalali_str(value)
    return jdatetime.date(*ymd) if ymd else None


def add_months(d, months: int):
    if d is None:
        return None
    y, m, day = add_months_ymd(d.year, d.month, d.day, months)
    return d.replace(year=y, month=m, day=day)


def add_days(d, days: int):
    import jdatetime
    return d + jdatetime.timedelta(days=days)


def days_between(later, earlier) -> int:
    return (later.togregorian() - earlier.togregorian()).days


def fmt(d) -> str:
    return d.strftime("%Y/%m/%d") if d else ""
