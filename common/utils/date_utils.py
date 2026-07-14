from datetime import date
from persiantools.jdatetime import JalaliDate


def to_jalali(value):
    """
    Gregorian -> Jalali
    """

    if value is None:
        return ""

    return JalaliDate(value)


def to_gregorian(year, month, day):
    """
    Jalali -> Gregorian
    """

    return JalaliDate(
        year,
        month,
        day,
    ).to_gregorian()