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