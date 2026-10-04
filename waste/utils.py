"""waste/utils.py -- shared CSV-import parsers. If you already pasted
parse_decimal / parse_iso_date directly into waste/views.py from the batch-
import round, delete those two definitions there and import from here instead
(both waste_import_csv and release_limit_import_csv use these)."""
import datetime
import decimal


def parse_decimal(value, field_name, errors, row_num):
    if value in (None, ""):
        return None
    try:
        return decimal.Decimal(str(value).strip())
    except (decimal.InvalidOperation, ValueError):
        errors.append(f"Row {row_num}: invalid number for {field_name}: '{value}'")
        return None


def parse_iso_date(value, field_name, errors, row_num):
    if value in (None, ""):
        return None
    try:
        return datetime.date.fromisoformat(value.strip())
    except ValueError:
        errors.append(f"Row {row_num}: invalid date for {field_name}: '{value}' (use YYYY-MM-DD)")
        return None