"""Pure helpers (no Django imports) so they can be unit-tested anywhere."""
from decimal import Decimal, InvalidOperation

from .jalali_utils import plan_week_ymd

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_NO_VALUE = {"", "-", "nd", "mdl", "bdl", "n/a", "na"}
_POSITIONS = {
    "body": "BODY", "بدن": "BODY", "تمام بدن": "BODY",
    "hand": "HAND", "دست": "HAND",
    "env": "ENV", "environment": "ENV", "environmental": "ENV", "محیط": "ENV", "محیطی": "ENV",
}


# ------------------------------------------------------------------ inspection plan
def current_week(plan_year, first_month, ty, tm, td):
    """0 = plan not started, total+1 = plan year is over."""
    total = (12 - first_month + 1) * 4
    if ty < plan_year:
        return 0
    if ty > plan_year:
        return total + 1
    return plan_week_ymd(tm, td, first_month)


def cell_state(period_weeks, week, is_done, current):
    """done / overdue / current / upcoming / off  (same colours as the Excel)."""
    if is_done:
        return "done"
    if (week - 1) % period_weeks != 0:
        return "off"
    if week < current:
        return "overdue"
    if week == current:
        return "current"
    return "upcoming"


def week_to_month_slot(week, first_month):
    return first_month + (week - 1) // 4, (week - 1) % 4 + 1


# ------------------------------------------------------------------ TLD paste import
def to_decimal(text):
    """None = 'no value' (blank, -, ND, MDL...). Raises ValueError for anything else."""
    s = str(text).strip().translate(_DIGITS).replace("٫", ".").replace("٬", "").replace("−", "-")
    if s.lower() in _NO_VALUE:
        return None
    if s.count(",") == 1 and "." not in s:
        s = s.replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(text)
    if not d.is_finite() or d < 0:
        raise ValueError(text)
    return d


def parse_tld_paste(text):
    """
    Lines: TLD code | worker code-or-name (or environmental point) | position | gamma | neutron | remarks
    Tab (Excel paste), ';' or ',' separated. A first line whose position is not recognised is a header.
    Returns (rows, errors); errors = [(line_no, message)].
    """
    rows, errors, first = [], [], True
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        delim = "\t" if "\t" in line else ";" if ";" in line else ","
        parts = [p.strip() for p in line.split(delim)]
        parts += [""] * (6 - len(parts))
        tld_code, ref, pos_txt, gamma_txt, neutron_txt, remarks = parts[:6]
        position = _POSITIONS.get(pos_txt.lower())
        if position is None:
            if first:
                first = False
                continue                                   # header row
            errors.append((no, f"unknown position '{pos_txt}' (use body / hand / environmental)"))
            continue
        first = False
        if not tld_code or not ref:
            errors.append((no, "TLD code and person/point are required"))
            continue
        try:
            gamma, neutron = to_decimal(gamma_txt), to_decimal(neutron_txt)
        except ValueError as e:
            errors.append((no, f"'{e}' is not a valid dose"))
            continue
        if gamma is None and neutron is None:
            errors.append((no, "both gamma and neutron are empty"))
            continue
        rows.append({"line": no, "tld_code": tld_code, "ref": ref, "position": position,
                     "gamma": gamma, "neutron": neutron, "remarks": remarks})
    return rows, errors
