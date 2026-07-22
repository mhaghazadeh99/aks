# NEW: Source type for filtering
# -----------------------------
from django.db import models
from django.utils.translation import gettext_lazy as _


class ActivityUnit(models.TextChoices):

    Bq = "Bq", _("Becquerel")
    KBq = "KBq", _("Kilobecquerel")
    MBq = "MBq", _("Megabecquerel")
    GBq = "GBq", _("Gigabecquerel")

    Ci = "Ci", _("Curie")
    mCi = "mCi", _("Millicurie")
    uCi = "uCi", _("Microcurie")
    nCI = "nCi", _("Nanocurie")