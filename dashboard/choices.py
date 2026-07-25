# NEW: Source type for filtering
# -----------------------------
from django.db import models
from django.utils.translation import gettext_lazy as _


class ActivityUnit(models.TextChoices):

    Bq = "Bq", "Bq"
    KBq = "KBq", "KBq"
    MBq = "MBq", "MBq"
    GBq = "GBq", "GBq"

    Ci = "Ci", "Ci"
    mCi = "mCi", "mCi"
    uCi = "uCi", "uCi"
    nCI = "nCi", "nCi"