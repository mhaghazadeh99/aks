"""
Pure-Python readers for the legacy Excel files (no Django imports, so they are
easy to test). Each returns plain dicts plus a list of human-readable warnings.
"""
from openpyxl import load_workbook

from .jalali_utils import parse_jalali_str

PERIOD_WEEKS = {"هفتگی": 1, "دوهفته یکبار": 2, "ماهانه": 4, "دو ماهه": 8, "سه ماهه": 12, "شش ماهه": 24}
STATUS_MAP = {"فعال": "ACTIVE", "غیرفعال": "INACTIVE", "ارسال به کالیبراسیون": "SENT"}
CENTER_MAP = {"تهران": "TEHRAN", "کرج": "KARAJ", "انارک": "ANARAK"}
LABEL_MAP = {"calibrated": "CALIBRATED", "rejected": "REJECTED", "out of service": "OUT_OF_SERVICE",
             "cbu": "CBU", "تصدیق": "VERIFICATION"}
LOAN_WORD = "امانت"


def clean(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = " ".join(str(v).split())
    return "" if s == "-" else s


# ------------------------------------------------------------------ equipment
def read_equipment(path):
    wb = load_workbook(path, read_only=True, data_only=False)
    warnings = []

    labels = {}
    if "Sheet1" in wb.sheetnames:
        for r in wb["Sheet1"].iter_rows(min_row=2, values_only=True):
            if r and r[1] and r[7]:
                labels[clean(r[1])] = LABEL_MAP.get(clean(r[7]).lower(), "")

    rows, empty_streak = [], 0
    ws = wb["لیست تجهیزات"]
    for n, r in enumerate(ws.iter_rows(min_row=2, max_col=18, values_only=True), start=2):
        if not r[1] and not r[2]:               # the sheet's used range is ~115k rows; stop at the gap
            empty_streak += 1
            if empty_streak > 40:
                break
            continue
        empty_streak = 0
        eq_id = clean(r[2])
        if not eq_id:
            warnings.append(f"row {n}: '{clean(r[1])}' has no equipment ID - skipped")
            continue

        status_raw, center_raw = clean(r[7]), clean(r[8])
        status, loan_to = STATUS_MAP.get(status_raw, ""), ""
        if LOAN_WORD in status_raw:
            status, loan_to = "LOAN", status_raw.replace(LOAN_WORD, "", 1).replace("به", "", 1).strip()
        if not status:
            status = "ACTIVE"
            warnings.append(f"{eq_id}: unknown status '{status_raw}' - set to Active")
        center = CENTER_MAP.get(center_raw, "")
        if center_raw and not center:
            warnings.append(f"{eq_id}: center '{center_raw}' is not Tehran/Karaj/Anarak - left blank")

        cal_raw = clean(r[12])
        ymd = parse_jalali_str(cal_raw) if cal_raw else None
        if cal_raw and not ymd:
            warnings.append(f"{eq_id}: invalid calibration date '{cal_raw}' - ignored")

        period = r[13] if isinstance(r[13], (int, float)) and r[13] else 12
        rows.append({
            "name": clean(r[1]), "equipment_id": eq_id, "model_name": clean(r[3]),
            "serial_number": clean(r[4]), "manufacturer": clean(r[5]), "application": clean(r[6]),
            "status": status, "loan_to": loan_to, "center": center,
            "current_location": clean(r[9]) if LOAN_WORD not in clean(r[9]) else "",
            "laboratory": clean(r[10]), "certificate_number": clean(r[11]),
            "last_calibration": ymd,                      # (y, m, d) or None
            "period_months": int(period), "notes": clean(r[17]),
            "label": labels.get(eq_id, ""),
        })
    ids = [x["equipment_id"] for x in rows]
    for dup in {i for i in ids if ids.count(i) > 1}:
        warnings.append(f"{dup}: appears more than once - the last row wins")
    return rows, warnings


# ------------------------------------------------------------------ inspection plan
def read_plan(path, sheet="برنامه سالانه", first_data_row=4, first_week_col=7, weeks=44):
    wb = load_workbook(path, data_only=False)
    ws = wb[sheet]
    warnings, items = [], []
    title = ""
    for n in range(first_data_row, ws.max_row + 1):
        area, period_txt = clean(ws.cell(n, 5).value), clean(ws.cell(n, 6).value)
        if not area and not period_txt:                 # footer / legend starts here
            break
        title = clean(ws.cell(n, 1).value) or title      # titles are merged-style: blank = same as above
        period = PERIOD_WEEKS.get(period_txt)
        if not period:
            warnings.append(f"row {n}: unknown period '{period_txt}' - skipped")
            continue
        done = [w for w in range(1, weeks + 1)
                if clean(ws.cell(n, first_week_col + w - 1).value) == "✓"]
        items.append({
            "title": title, "form_title": clean(ws.cell(n, 2).value),
            "form_code": clean(ws.cell(n, 3).value), "responsible": clean(ws.cell(n, 4).value),
            "area": area, "period_weeks": period, "done_weeks": done,
        })
    # fill a missing form code from another row that uses the same form
    codes = {i["form_title"]: i["form_code"] for i in items if i["form_code"]}
    for i in items:
        if not i["form_code"] and codes.get(i["form_title"]):
            warnings.append(f"'{i['title']} / {i['area']}': form code was empty, filled with {codes[i['form_title']]}")
            i["form_code"] = codes[i["form_title"]]
        elif not i["form_code"]:
            warnings.append(f"'{i['title']} / {i['area']}': form code is empty")
    return items, warnings
