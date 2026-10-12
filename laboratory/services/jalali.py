"""
laboratory/services/jalali.py -- Gregorian -> Jalali (Solar Hijri / Shamsi) dates.

Pure Python, no extra package. Checked against: 2026-03-21 -> 1405/01/01 (Nowruz),
2026-03-20 -> 1404/12/29, 2026-10-10 -> 1405/07/18.
"""

import datetime

from django.utils import timezone

_PERSIAN_DIGITS = str.maketrans("0123456789", "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9")


def as_date(value):
    """date / datetime (aware or naive) -> datetime.date in the project's local time zone."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.date()
    return value


def gregorian_to_jalali(gy, gm, gd):
    g_d_m = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400)
        + gd + g_d_m[gm - 1]
    )
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def format_jalali(value, persian_digits=True, sep="/"):
    """1405/07/18 style string, or "" for empty. persian_digits=True gives
    \u06f1\u06f4\u06f0\u06f5/\u06f0\u06f7/\u06f1\u06f8 -- the same digits the signature rows use."""
    d = as_date(value)
    if d is None:
        return ""
    jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
    text = f"{jy:04d}{sep}{jm:02d}{sep}{jd:02d}"
    return text.translate(_PERSIAN_DIGITS) if persian_digits else text


# ---------------------------------------------------------------------
# Parsing (used by the CSV import)
# ---------------------------------------------------------------------

_TO_LATIN_DIGITS = str.maketrans(
    "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9"      # Persian
    "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669",     # Arabic-Indic
    "01234567890123456789",
)


def latin_digits(text):
    """Persian / Arabic-Indic digits -> 0-9 (Arabic decimal separator too)."""
    return str(text).translate(_TO_LATIN_DIGITS).replace("\u066b", ".").replace("\u066c", "")


def jalali_to_gregorian(jy, jm, jd):
    jy += 1595
    days = (
        -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
        + ((jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186)
    )
    gy = 400 * (days // 146097)
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
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    month_days = (0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    gm = 0
    while gm < 13 and gd > month_days[gm]:
        gd -= month_days[gm]
        gm += 1
    return gy, gm, gd


def parse_date(text):
    """'1405/07/18', '۱۴۰۵-۰۷-۱۸', '2026-10-10', '2026/10/10' -> datetime.date.
    A year below 1700 is read as Jalali, otherwise Gregorian. Raises ValueError with a
    readable message on anything else (including impossible dates such as 1405/12/30 in a
    non-leap year)."""
    import re
    raw = latin_digits(text).strip()
    m = re.fullmatch(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", raw)
    if not m:
        raise ValueError(f"'{text}' is not a date (use 1405/07/18 or 2026-10-10)")
    y, mo, d = (int(g) for g in m.groups())
    if y < 1700:
        if not (1 <= mo <= 12 and 1 <= d <= (31 if mo <= 6 else 30 if mo <= 11 else 30)):
            raise ValueError(f"'{text}' is not a valid Jalali date")
        gy, gm, gd = jalali_to_gregorian(y, mo, d)
        result = datetime.date(gy, gm, gd)          # raises ValueError if impossible
        if gregorian_to_jalali(gy, gm, gd) != (y, mo, d):
            raise ValueError(f"'{text}' is not a valid Jalali date (month {mo} has no day {d} that year)")
        return result
    try:
        return datetime.date(y, mo, d)
    except ValueError:
        raise ValueError(f"'{text}' is not a valid date")