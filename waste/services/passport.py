import datetime
import os
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# =====================================================
# Units: key -> (label shown, factor to the BASE unit)
# Bases: activity Bq | mass kg | volume m3 | dose rate uSv/h
#        contamination Bq/cm2 | half-life seconds (as stored)
# =====================================================

YEAR_S = 365.25 * 86400

UNIT_GROUPS = {
    "act_unit": ("Activity", "GBq", {
        "Bq": ("Bq", 1.0), "kBq": ("kBq", 1e3), "MBq": ("MBq", 1e6),
        "GBq": ("GBq", 1e9), "TBq": ("TBq", 1e12),
        "uCi": ("µCi", 3.7e4), "mCi": ("mCi", 3.7e7), "Ci": ("Ci", 3.7e10),
    }),
    "mass_unit": ("Mass", "kg", {
        "g": ("g", 1e-3), "kg": ("kg", 1.0), "t": ("t", 1e3),
    }),
    "vol_unit": ("Volume", "m3", {
        "cm3": ("cm³", 1e-6), "L": ("L", 1e-3), "m3": ("m³", 1.0),
    }),
    "dose_unit": ("Dose rate", "mSv/h", {
        "nSv/h": ("nSv/h", 1e-3), "uSv/h": ("µSv/h", 1.0),
        "mSv/h": ("mSv/h", 1e3), "Sv/h": ("Sv/h", 1e6),
        "mrem/h": ("mrem/h", 10.0),
    }),
    "cont_unit": ("Surface contamination", "Bq/cm2", {
        "Bq/cm2": ("Bq/cm²", 1.0), "Bq/m2": ("Bq/m²", 1e4),
        "dpm/cm2": ("dpm/cm²", 60.0),
    }),
    "hl_unit": ("Half-life", "y", {
        "s": ("s", 1.0), "h": ("h", 3600.0), "d": ("d", 86400.0), "y": ("y", YEAR_S),
    }),
}


def unit_groups_for_template():
    """[(field, label, default, [(key, label), ...]), ...] for the options page."""
    return [
        (field, title, default, [(k, v[0]) for k, v in choices.items()])
        for field, (title, default, choices) in UNIT_GROUPS.items()
    ]


def units_from_request(data):
    chosen = {}
    for field, (_t, default, choices) in UNIT_GROUPS.items():
        key = data.get(field, default)
        chosen[field] = key if key in choices else default
    return chosen


def _conv(value, field, units, from_factor=1.0):
    """value in BASE unit (times from_factor) -> chosen unit."""
    if value is None:
        return None
    label, factor = UNIT_GROUPS[field][2][units[field]]
    return float(value) * from_factor / factor


def _label(field, units):
    return UNIT_GROUPS[field][2][units[field]][0]


# =====================================================
# Number formatting
# =====================================================

def fmt(v, sig=7):
    if v is None or v == "":
        return "-"
    if isinstance(v, (int, float)) or hasattr(v, "quantize"):
        v = float(v)
        if v == 0:
            return "0"
        if abs(v) < 1e-4 or abs(v) >= 1e9:
            return f"{v:.{sig - 1}e}"
        return f"{v:.{sig}g}"
    return str(v)


# =====================================================
# Data
# =====================================================

def nuclide_rows(batch):
    """[{name, initial_bq, current_bq, half_life_s}] for the batch's latest gamma analysis.

    The lab stores raw activity for the SAMPLE. The batch-level (per package) figure
    comes from batch.activity_breakdown()["gamma_total_bq"], so each nuclide is
    scaled by (package gamma total today / sum of the sample's decayed nuclide activities).
    ASSUMPTION: gamma_total_bq is decay-corrected to today -- replace this with the
    real per-nuclide numbers from laboratory/services/activity.py once available.
    """
    activities = batch.nuclide_activities()
    if not activities:
        return []

    decayed = [(na.current_activity_bq() or 0.0) for na in activities]
    gamma_now = batch.activity_breakdown().get("gamma_total_bq")
    total_decayed = sum(decayed)
    k = float(gamma_now) / total_decayed if gamma_now and total_decayed > 0 else 1.0

    return [
        {
            "name": str(na.radionuclide),
            "initial_bq": float(na.activity_bq) * k,
            "current_bq": dec * k,
            "half_life_s": na.radionuclide.half_life,   # seconds
        }
        for na, dec in zip(activities, decayed)
    ]


def nuclide_export_text(batch, unit_key="GBq"):
    """'Cs-137=2.05e-03 GBq; Cs-134=...' for CSV / Excel."""
    label, factor = UNIT_GROUPS["act_unit"][2][unit_key]
    parts = [f"{r['name']}={r['current_bq'] / factor:.6g}" for r in nuclide_rows(batch)]
    return "; ".join(parts)


# =====================================================
# Fonts (Greek letters need a real TTF; Arial ships with Windows)
# =====================================================

def _register_fonts():
    candidates = [
        (getattr(settings, "PASSPORT_FONT", None), getattr(settings, "PASSPORT_FONT_BOLD", None)),
        (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for regular, bold in candidates:
        if regular and bold and os.path.exists(regular) and os.path.exists(bold):
            pdfmetrics.registerFont(TTFont("PP", regular))
            pdfmetrics.registerFont(TTFont("PP-B", bold))
            return "PP", "PP-B"
    return "Helvetica", "Helvetica-Bold"      # Greek letters will not render


# =====================================================
# PDF
# =====================================================

GREY = colors.HexColor("#b8c4cc")
LINE = colors.HexColor("#555555")


def build_passport_pdf(batches, units, serial_prefix="", logo_path=None):
    regular, bold = _register_fonts()
    today = timezone.localdate()

    st_label = ParagraphStyle("lbl", fontName=bold, fontSize=9, leading=11, alignment=TA_CENTER)
    st_val = ParagraphStyle("val", fontName=regular, fontSize=9, leading=11, alignment=TA_CENTER)
    st_title = ParagraphStyle("ttl", fontName=bold, fontSize=15, leading=19, alignment=TA_CENTER)
    st_left = ParagraphStyle("lft", fontName=regular, fontSize=10, leading=14)
    st_sec = ParagraphStyle("sec", fontName=bold, fontSize=11, leading=14, alignment=TA_CENTER)

    def P(text, style):
        return Paragraph(escape("" if text is None else str(text)).replace("\n", "<br/>"), style)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            title="Passport on Radioactive Waste Package")
    W = A4[0] - 24 * mm

    def grid(items):
        """items = [(label, value)...] -> one label row + one value row per 4 items."""
        story = []
        for i in range(0, len(items), 4):
            chunk = items[i:i + 4]
            while len(chunk) < 4:
                chunk.append(("", ""))
            t = Table([[P(l, st_label) for l, _ in chunk], [P(v, st_val) for _, v in chunk]],
                      colWidths=[W / 4] * 4, rowHeights=[9 * mm, 11 * mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), GREY),
                ("GRID", (0, 0), (-1, -1), 0.7, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story += [t, Spacer(1, 3 * mm)]
        return story

    def header(serial):
        left = [P(f"Report Date&nbsp;&nbsp;{today:%d %b %Y}", st_left), Spacer(1, 5 * mm),
                P(f"Serial No.&nbsp;&nbsp;{escape(serial)}", st_left)]
        logo = ""
        if logo_path and os.path.exists(logo_path):
            logo = Image(logo_path, width=22 * mm, height=22 * mm, kind="proportional")
        t = Table([[left, P("Passport on Radioactive Waste Package\nIRWA Co.", st_title), logo]],
                  colWidths=[W * 0.28, W * 0.50, W * 0.22], rowHeights=[28 * mm])
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, LINE),
                               ("LINEAFTER", (0, 0), (1, 0), 0.8, LINE),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        return [t, Spacer(1, 4 * mm)]

    act = _label("act_unit", units)
    story = []

    for n, b in enumerate(batches, start=1):
        gamma = b.latest_gamma_analysis
        ab = b.latest_alpha_beta_analysis
        bd = b.activity_breakdown()
        rows = nuclide_rows(b)

        story += header(f"{serial_prefix}{today:%Y%m%d}-{b.pk}")

        pkg_mass = b.package_mass_kg if b.package_mass_kg is not None else b.mass_kg
        pkg_vol = b.package_volume_m3 if b.package_volume_m3 is not None else b.volume_m3

        story += grid([
            ("Waste ID", b.waste_id),
            ("Origin Facility", b.origin_facility or "-"),
            ("Facility", b.facility),
            ("Waste Type", b.get_waste_type_display()),
        ])
        story += grid([
            ("Container Name", b.container_type or "-"),
            ("Analysis Protocol ID", gamma.sample.sample_id if gamma else ""),
            (f"Package Volume ({_label('vol_unit', units)})", fmt(_conv(pkg_vol, "vol_unit", units))),
            (f"Package Mass ({_label('mass_unit', units)})", fmt(_conv(pkg_mass, "mass_unit", units))),
        ])
        story += grid([
            ("Received Date", b.date_received.strftime("%Y/%m/%d") if b.date_received else "-"),
            ("Waste Arising From", b.waste_arising_from or "-"),
            ("Waste Status", b.get_status_display().split(" (")[0]),
            ("Waste Description", b.description or "-"),
        ])
        story += grid([
            ("Pretreatment Type", b.get_pretreatment_display() or "N/A"),
            ("Treatment Type", b.get_treatment_display() or "N/A"),
            (f"α Contam. {_label('cont_unit', units)}", fmt(_conv(b.alpha_contamination_bq_cm2, "cont_unit", units))),
            (f"β γ Contam. {_label('cont_unit', units)}", fmt(_conv(b.beta_gamma_contamination_bq_cm2, "cont_unit", units))),
        ])
        du = _label("dose_unit", units)
        story += grid([
            ("RW Classification", b.waste_class or "-"),
            (f"Dose Rate Cont. {du}", fmt(_conv(b.dose_rate_surface_uSv, "dose_unit", units))),
            (f"Dose Rate 1 m {du}", fmt(_conv(b.dose_rate_1m_uSv, "dose_unit", units))),
            ("Measurement Date", b.dose_rate_date.strftime("%Y/%m/%d") if b.dose_rate_date else "-"),
        ])

        # ---- nuclide table ----
        story += [Spacer(1, 2 * mm), P("Identified Radionuclides", st_sec), Spacer(1, 2 * mm)]
        data = [[P("", st_label), P("Radionuclide", st_label), P(f"Activity {act}/Package", st_label),
                 P(f"Current Activity {act}/Package", st_label), P(f"Half Life ({_label('hl_unit', units)})", st_label)]]
        tot_i = tot_c = 0.0
        for i, r in enumerate(rows, start=1):
            tot_i += r["initial_bq"]
            tot_c += r["current_bq"]
            data.append([
                P(i, st_val), P(r["name"], st_val),
                P(fmt(_conv(r["initial_bq"], "act_unit", units)), st_val),
                P(fmt(_conv(r["current_bq"], "act_unit", units)), st_val),
                P(fmt(_conv(r["half_life_s"], "hl_unit", units), 6), st_val),   # stored in seconds
            ])
        data.append([P("", st_val), P("Total Activity", st_label),
                     P(fmt(_conv(tot_i, "act_unit", units)) if rows else "-", st_label),
                     P(fmt(_conv(tot_c, "act_unit", units)) if rows else "-", st_label), P("", st_val)])
        t = Table(data, colWidths=[W * 0.06, W * 0.22, W * 0.26, W * 0.28, W * 0.18], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GREY),
            ("GRID", (0, 0), (-1, -1), 0.7, LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story += [t, Spacer(1, 3 * mm)]

        # ---- gross alpha / beta ----
        ab_date = ab.analysis_date.strftime("%Y/%m/%d") if ab and ab.analysis_date else ""
        t = Table([
            [P(f"Total α Activity {act}/Package", st_label), P(f"Total β γ Activity {act}/Package", st_label),
             P("Alpha Beta Activity Date", st_label)],
            [P(fmt(_conv(bd.get("gross_alpha_bq"), "act_unit", units)) if bd.get("gross_alpha_bq") is not None else "0", st_val),
             P(fmt(_conv(bd.get("gross_beta_bq"), "act_unit", units)) if bd.get("gross_beta_bq") is not None else "0", st_val),
             P(ab_date, st_val)],
        ], colWidths=[W * 0.34, W * 0.34, W * 0.32], rowHeights=[9 * mm, 12 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), GREY), ("GRID", (0, 0), (-1, -1), 0.7, LINE),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(t)

        if n < len(batches):
            story.append(PageBreak())

    doc.build(story)
    return buf.getvalue()
