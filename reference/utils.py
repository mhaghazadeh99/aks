from django.utils.translation import gettext_lazy as _


def parse_float(value, field_name, errors, row_number):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        errors.append(
            _("Row %(row)s: Invalid float for %(field)s") % {
                "row": row_number,
                "field": field_name
            }
        )
        return None


def parse_int(value, field_name, errors, row_number):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        errors.append(
            _("Row %(row)s: Invalid integer for %(field)s") % {
                "row": row_number,
                "field": field_name
            }
        )
        return None


def parse_bool(value):
    if value in (True, False):
        return value

    if value is None:
        return False

    value = str(value).strip().lower()

    return value in ["1", "true", "yes", "y"]