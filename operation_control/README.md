# operation_control

Equipment calibration · Dosimetry (TLD + online) · Inspection plan — with Excel/CSV import and export.

## Install
1. settings.py  -> INSTALLED_APPS += ["operation_control"]
   (needs crispy_forms, simple_history and openpyxl — no django_jalali)
2. urls.py      -> path("operation-control/", include("operation_control.urls"))
3. python manage.py makemigrations operation_control && python manage.py migrate
4. Paste the cards from control_home_snippet.html into your control_home.html
5. python manage.py makemessages -l fa      # Persian strings

## Importing your data (web: every list page has "Import CSV"; same code on the command line)
Each import accepts your ORIGINAL .xlsx (the right sheet is found automatically) or a CSV, with English
or Persian headers, Jalali or Gregorian dates, Persian digits. A CSV template can be downloaded on each import page.
Always tick "Preview only" first: it shows exactly what would happen and saves nothing.

| Part                  | Source                                   | Import page            |
|-----------------------|------------------------------------------|------------------------|
| Equipment+calibration | calibration workbook "لیست تجهیزات"      | /import/equipment/     |
| Workers               | dose workbook "پرسنل"                    | /import/workers/       |
| TLD readings          | dose workbook "ثبت دز"                   | /import/tld/           |
| Online doses          | CSV (new data, no Excel yet)             | /import/online_doses/  |
| Inspection plan       | plan workbook "برنامه سالانه"            | /import/inspection/    |
| Interval assessments  | calibration workbook "برگه ارزیابی"       | /import/assessments/   |

Suggested order: workers -> equipment -> assessments -> TLD readings -> plan.

Command line (same logic, `--dry-run` supported):
  python manage.py import_operation_control --workers dose.xlsx --equipment calib.xlsx --tld dose.xlsx --plan plan.xlsx --dry-run

Rules worth knowing
* Existing records (same equipment ID / personnel code / TLD code in a report / inspection title+area) are UPDATED, new ones created.
* A single "مقدار دز" column is imported as GAMMA dose; doses in µSv are converted to mSv.
* Calibration period 0 / empty / text becomes 12 months with a warning (text is kept in the notes).
* Online-dose operations that already exist (same date + operation + location) are skipped, so re-importing is safe.
* "All or nothing" saves nothing if any row has an error; otherwise good rows are saved and bad rows are listed.

## Reading the OLD SQL Server database (HealthPhysics)
Direct (read-only SELECTs; `pip install pyodbc` + Microsoft's "ODBC Driver 17/18 for SQL Server"):
  python manage.py import_legacy_dosimetry --tld --dry-run --connection "DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;DATABASE=HealthPhysics;Trusted_Connection=yes;"
  (or set OPERATION_CONTROL_LEGACY_SQL in settings.py and drop --connection; --print-sql shows the query)
Without a connection from the server: run legacy_tld_query.sql in SSMS, save the grid as CSV, then
TLD reports -> "Import from the old system". Both ways use the same code.
Rules: dates in DateD are Jalali; the season of a report is the season of the MIDDLE of Date1..Date2.
DoseID 3 total effective / 4 photon (gamma) / 5 hand / 10 neutron are merged per person per report
(total-only rows are imported as gamma). Personnel are matched to workers by first + last name
(then PNumber = personnel code); personnel matching nobody (the old "case studies") become environmental points.
Several lab reports may share a season: they stay separate and their doses add up in the season totals.

Online doses (`--online`, or Operation dose records -> "Import from the old system", query in legacy_online_query.sql):
  Place name -> operation, centre name + address -> location, DateTime -> operation date (Jalali),
  DureofTime -> operation duration (also each person's exposure time). Same date + place + duration = one operation.
  The old table has no device, dose type or unit: doses are imported WITHOUT a device, as gamma, in uSv
  (choose mSv with --online-unit msv or on the import page). People matching no worker are skipped and listed.
  Each imported dose keeps its OnDoseID, so importing again updates instead of duplicating.

## Calibration interval assessment (OIML D10 scoring)
A port of your "برگه ارزیابی" + "جداول امتیازدهی" sheets (tested against your Excel's own results): 7 factors ->
total /100 -> level and interval (6/12/24/36 months) + the auto-written audit justification.
Open a device -> "New assessment"; "Apply" copies the interval to the device and recalculates its due date.
(The "جدول_ضرایب" coefficient table is not used by your assessment sheet's formulas, so it is not implemented.)

## Notifications
{% calibration_alert %} shows a banner for devices that are expired or expire within 30 days (active / loaned devices).
It is on the equipment pages; add the tag at the top of control_home.html (see control_home_snippet.html).

## Inspection plan
Click a cell -> tick it as done: who did it (workers), optional evidence file(s) and a note; the date defaults to today.
Evidence files are optional (OPERATION_CONTROL_INSPECTION_REQUIRE_ATTACHMENT = True makes at least one mandatory).
Responsible people and "done by" are radiation workers, not users.

## Exports (CSV, re-importable): equipment, workers, TLD readings, online doses, inspection plan

## Optional settings
OPERATION_CONTROL_LEGACY_SQL = "DRIVER={ODBC Driver 17 for SQL Server};SERVER=...;DATABASE=HealthPhysics;Trusted_Connection=yes;"
OPERATION_CONTROL_SEASON_DOSE_LIMIT_MSV = 1.5
OPERATION_CONTROL_ANNUAL_DOSE_LIMIT_MSV = 20
OPERATION_CONTROL_CALIBRATION_WARNING_DAYS = 30
OPERATION_CONTROL_INSPECTION_REQUIRE_ATTACHMENT = False

## Pick-lists (in the app): operation types, environmental TLD points, equipment applications.

## Tests
python manage.py test operation_control
