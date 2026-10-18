"""Texts shown on the import pages (translatable)."""
from django.utils.translation import gettext_lazy as _

R, O = True, False

SPECS = {
    "equipment": {
        "title": _("Import equipment & calibrations"),
        "back": "oc_equipment_list",
        "intro": _("Upload your original calibration workbook (.xlsx — the “لیست تجهیزات” sheet and the labels on Sheet1 are read automatically) or a CSV. "
                   "Existing equipment (same equipment ID) is updated, new equipment is created. "
                   "A last-calibration date adds a calibration record (once)."),
        "columns": [
            ("equipment_id", R, _("Unique ID, e.g. PH-0001E1 (شماره شناسایی تجهیز)")),
            ("name", R, _("Device name (نام دستگاه)")),
            ("model_name / serial_number / manufacturer", O, _("مدل / شماره سریال / سازنده")),
            ("application", O, _("Application, created if new (کاربرد دستگاه)")),
            ("status", O, _("Active / Inactive / Sent for calibration / “امانت به …” (on loan)")),
            ("center", O, _("Tehran / Karaj / Anarak")),
            ("current_location", O, _("Where the device is now")),
            ("calibration_period_months", O, _("Months; 0, empty or text becomes 12 with a warning")),
            ("current_label", O, _("Calibrated / Rejected / Out of service / CBU / Verification")),
            ("last_calibration_date", O, _("Jalali 1402/09/15 or Gregorian 2026-07-15")),
            ("certificate_number / laboratory / calibration_type", O, _("Stored on the calibration record")),
            ("notes", O, _("Notes / action")),
        ],
    },
    "workers": {
        "title": _("Import radiation workers"),
        "back": "oc_worker_list",
        "intro": _("Upload the “پرسنل” sheet of your dose workbook (.xlsx) or a CSV. "
                   "Workers are matched by personnel code: existing ones are updated, new ones created."),
        "columns": [
            ("personnel_code", R, _("Personnel code (کد پرسنلی)")),
            ("full_name", R, _("Full name (نام و نام خانوادگی)")),
            ("unit / position", O, _("واحد / بخش، سمت")),
            ("status", O, _("Active (فعال) or Left (غیرفعال / خارج شده …)")),
            ("exit_date", O, _("Jalali or Gregorian date")),
            ("notes", O, _("Notes")),
        ],
    },
    "tld": {
        "title": _("Import TLD readings"),
        "back": "oc_tld_report_list",
        "intro": _("Upload the “ثبت دز” sheet of your dose workbook (.xlsx) or a CSV. One TLD per row. "
                   "Reports are created per Jalali year + season. A single “مقدار دز” column is imported as gamma dose; "
                   "use gamma_msv / neutron_msv to give both. Doses in µSv are converted to mSv. Rows with no worker/TLD/dose (pre-filled template rows) are ignored."),
        "columns": [
            ("year, season", R, _("Jalali year and season (بهار / تابستان / پاییز / زمستان)")),
            ("report_number, received_date", O, _("Lab report number and the date it was received")),
            ("tld_code", R, _("TLD code (کد TLD) — unique within a report")),
            ("personnel_code / full_name", O, _("Worker, for body and hand TLDs. With both, a missing worker can be created")),
            ("env_point", O, _("Environmental point name, for environmental TLDs")),
            ("position", O, _("body / hand / environmental (default body, or environmental when env_point is given)")),
            ("gamma_msv, neutron_msv", O, _("Doses (at least one). Blank, -, ND, MDL = no value")),
            ("unit", O, _("mSv (default) or µSv")),
            ("remarks", O, _("Remarks")),
        ],
    },
    "online_doses": {
        "title": _("Import online dose records"),
        "back": "oc_session_list",
        "intro": _("CSV (or .xlsx) with one row per worker and dose type. Rows with the same date + operation + location "
                   "become one operation. Workers and devices must already exist; an operation that already exists is skipped, so re-importing the same file is safe."),
        "columns": [
            ("date", R, _("Operation date, Jalali or Gregorian")),
            ("operation", R, _("Operation type (from the pick-list; new names can be created)")),
            ("location / operation_duration_min / description", O, _("Operation details (taken from the first row of each operation)")),
            ("session", O, _("Optional ID to keep two same-day operations apart")),
            ("personnel_code / full_name", R, _("Worker")),
            ("device", R, _("Equipment ID or serial number of the dosimeter")),
            ("dose_type", R, _("gamma or neutron (گاما / نوترون)")),
            ("dose_value, unit", R, _("Recorded dose; unit uSv (default) or mSv")),
            ("exposure_minutes", O, _("Minutes in which the dose was received")),
        ],
    },
    "assessments": {
        "title": _("Import calibration assessments"),
        "back": "oc_assessment_list",
        "intro": _("Upload the “برگه ارزیابی” sheet of your calibration workbook (.xlsx) or a CSV. Points, totals, levels and the audit "
                   "justification are calculated by the app (the same method as your sheet), only the answers are read. "
                   "Rows the sheet marks as a sample are skipped. The device is found by equipment ID, or by exact device name / model."),
        "columns": [
            ("equipment_id", R, _("Equipment ID — or the device name / model used in your sheet (نام / کد تجهیز)")),
            ("device_type", R, _("Portable (قابل حمل) / Fixed (غیر قابل حمل)")),
            ("has_maker_recommendation, maker_recommendation", O, _("yes/no (بله/خیر) and Six months / One year / Two years / Three years")),
            ("accuracy", R, _("Low / Medium / High / Very high (MSA results)")),
            ("environment", R, _("Very good / Good / Medium / Bad")),
            ("importance, wear, cost", R, _("Very high / High / Medium / Low")),
            ("assessment_date, assessed_by", O, _("Date (default today) and the worker's personnel code")),
            ("notes", O, _("Notes")),
        ],
    },
    "inspection": {
        "title": _("Import inspection plan"),
        "back": "oc_inspection_plan",
        "intro": _("Upload your original plan workbook (.xlsx — the ticks become done-marks for the year in its title) or a CSV. "
                   "Items are matched by title + area. In a CSV, put week numbers in done_weeks (e.g. 1,3,5 or 1-4)."),
        "columns": [
            ("title, area", R, _("Inspection title (blank = same as the row above) and area")),
            ("period", R, _("Weekly / Every two weeks / Monthly / Every two months / Every three months / Every six months (or Persian)")),
            ("form_title, form_code", O, _("Checklist / form and its code")),
            ("responsible", O, _("Worker: personnel code or full name")),
            ("is_active", O, _("yes / no")),
            ("done_weeks, plan_year", O, _("Done weeks of the plan year (the form's year is used if plan_year is empty)")),
        ],
    },
}
