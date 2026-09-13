"""
Fills the scanned "DSRS sale request" form's MIDDLE table (the
"شرکت مدیریت پسماندهای پرتوزای ایران" / IRWA section) with the sources
added to a SellRequest, and — once the CEO has signed — overlays their
signature image and the sign-off date into the stamp box right below
that table.

CALIBRATION — measured directly against the reference scan you
uploaded (2196 x 3191 px, a CamScanner-processed A4 page). Coordinates
are stored as FRACTIONS of image width/height, not fixed pixels, and
applied proportionally to whatever size is actually uploaded. Since
every scan is the same A4 page (aspect ratio 1:1.41) and CamScanner's
auto-crop/deskew tends to frame the page consistently, this should hold
up reasonably well across different scans of the same physical form —
but it IS still calibrated against one example, so if text starts
landing in the wrong cells after a batch of real submissions, re-measure
against a fresh scan (see the measurement approach in this file's
history / ask for it to be redone).

REQUIRES, on the actual server (not available in the sandbox this was
written in, so the Persian rendering below is unverified — test it
before relying on it):
    pip install arabic-reshaper python-bidi Pillow
and a real Persian-capable .ttf font file, path set via:
    settings.SELL_SOURCE_PERSIAN_FONT_PATH = "/path/to/Vazirmatn-Regular.ttf"
(or your existing "B Nazanin" file, wherever the docx generator's font
lives). Without arabic_reshaper/python-bidi installed, Persian text will
still get drawn, but the letters will render disconnected and in the
wrong (LTR) order — this module falls back to drawing raw text rather
than crashing, but it will NOT look right until those are installed.
"""

import os
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    RTL_AVAILABLE = True
except ImportError:
    RTL_AVAILABLE = False


# =====================================================================
# Jalali date (duplicated from receiving/services/specification_generator.py
# — small enough, and keeps this app independent of the receiving app)
# =====================================================================

_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _to_persian_digits(text):
    if text is None:
        return ""
    return str(text).translate(_PERSIAN_DIGITS)


def _gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
        + g_d_m[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + (days % 31)
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def _format_jalali_date(date_obj):
    if date_obj is None:
        return ""
    dt = date_obj.date() if hasattr(date_obj, "date") else date_obj
    jy, jm, jd = _gregorian_to_jalali(dt.year, dt.month, dt.day)
    return _to_persian_digits(f"{jy:04d}/{jm:02d}/{jd:02d}")


def _shape(text):
    """Reshape+reorder Persian/Arabic text for correct rendering as an
    image (raw PIL draws each letter isolated and left-to-right, which
    is wrong for Persian) — see module docstring for the required
    packages. Falls back to raw text if they aren't installed."""
    if not text:
        return ""
    if not RTL_AVAILABLE:
        return str(text)
    reshaped = arabic_reshaper.reshape(str(text))
    return get_display(reshaped)


# =====================================================================
# CALIBRATION — fractions of (width, height), measured against the
# reference scan. See module docstring.
# =====================================================================

COLUMNS = {
    "remarks": (0.0542, 0.2887),    # ملاحظات
    "serial": (0.2892, 0.3411),     # شماره سریال چشمه
    "activity": (0.3416, 0.5160),   # پرتوزایی ثبت شده (mCi)
    "mfg_date": (0.5164, 0.5993),   # تاریخ ساخت
    "physical": (0.5998, 0.7373),   # مشخصات فیزیکی
    "nuclide": (0.7373, 0.8452),    # نام ماده پرتوزا
}

ROWS = [
    (0.4871, 0.5080),
    (0.5080, 0.5250),
    (0.5250, 0.5420),
    (0.5420, 0.5590),
    (0.5590, 0.5760),
]
MAX_TABLE_ROWS = len(ROWS)

# CEO stamp/signature box and its adjacent "تاریخ:" fill-in spot.
SIGNATURE_BOX = (0.0537, 0.5975, 0.2600, 0.6620)
SIGNATURE_DATE_BOX = (0.3200, 0.6650, 0.4500, 0.6900)

TEXT_COLOR = (20, 20, 130)
DEFAULT_FONT_SIZE =12

def _font(size):
    font_path = getattr(settings, "SELL_SOURCE_PERSIAN_FONT_PATH", None)
    if font_path and os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)
    # PIL's built-in default font cannot render Persian at all — this
    # only exists so the pipeline doesn't crash if the font isn't
    # configured yet; set SELL_SOURCE_PERSIAN_FONT_PATH for real use.
    return ImageFont.load_default()


def _draw_in_box(draw, image_size, box_fractions, text, font_size=DEFAULT_FONT_SIZE, shape=True):
    """box_fractions = (x0, y0, x1, y1) as fractions of image size.
    Centers `text` within that box."""
    if not text:
        return

    W, H = image_size
    x0f, y0f, x1f, y1f = box_fractions
    x0, y0, x1, y1 = x0f * W, y0f * H, x1f * W, y1f * H

    rendered = _shape(text) if shape else str(text)
    font = _font(font_size)

    bbox = draw.textbbox((0, 0), rendered, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

    cx = x0 + max((x1 - x0 - text_w) / 2, 4)
    cy = y0 + max((y1 - y0 - text_h) / 2, 2)

    draw.text((cx, cy), rendered, font=font, fill=TEXT_COLOR)


def _draw_cell(draw, image_size, col_key, row_bounds, text, font_size=DEFAULT_FONT_SIZE):
    x0f, x1f = COLUMNS[col_key]
    y0f, y1f = row_bounds
    _draw_in_box(draw, image_size, (x0f, y0f, x1f, y1f), text, font_size=font_size)


def regenerate_filled_form(sell_request):
    """
    Rebuilds `filled_form` from the pristine `request_form` every call —
    draws every current source row, and (if the CEO has signed) the
    signature image + date — rather than drawing on top of whatever was
    generated last time. Call this after adding/removing a source, and
    again right after the CEO signs.
    """

    if not sell_request.request_form:
        return None

    image = Image.open(sell_request.request_form.path).convert("RGB")
    draw = ImageDraw.Draw(image)
    size = image.size

    sources = list(
        sell_request.sources.select_related("nuclide").order_by("id")[:MAX_TABLE_ROWS]
    )

    for i, source in enumerate(sources):
        row_bounds = ROWS[i]
        _draw_cell(draw, size, "nuclide", row_bounds, str(source.nuclide) if source.nuclide else "")
        _draw_cell(draw, size, "physical", row_bounds, source.physical_characteristics)
        _draw_cell(draw, size, "mfg_date", row_bounds, _to_persian_digits(source.manufacture_date) if source.manufacture_date else "")
        _draw_cell(
            draw, size, "activity", row_bounds,
            _to_persian_digits(f"{source.recorded_activity_mci:.2f}") if source.recorded_activity_mci is not None else "",
        )
        _draw_cell(draw, size, "serial", row_bounds, source.serial_number)
        _draw_cell(draw, size, "remarks", row_bounds, source.remarks)

    if sell_request.ceo_approved_by_id:

        profile = getattr(sell_request.ceo_approved_by, "profile", None)

        if profile and profile.signature_image:
            W, H = size
            x0f, y0f, x1f, y1f = SIGNATURE_BOX
            box_w = int((x1f - x0f) * W)
            box_h = int((y1f - y0f) * H)

            sig = Image.open(profile.signature_image.path).convert("RGBA")
            sig.thumbnail((box_w, box_h))

            paste_x = int(x0f * W + (box_w - sig.width) / 2)
            paste_y = int(y0f * H + (box_h - sig.height) / 2)
            image.paste(sig, (paste_x, paste_y), sig)

        _draw_in_box(
            draw, size, SIGNATURE_DATE_BOX,
            _format_jalali_date(sell_request.ceo_approved_at),
            font_size=20,
            shape=False,  # digits only (Persian-digit string), no RTL reshaping needed
        )

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    buffer.seek(0)

    if sell_request.filled_form:
        sell_request.filled_form.delete(save=False)

    sell_request.filled_form.save(
        f"sell_request_{sell_request.pk}_filled.jpg",
        ContentFile(buffer.read()),
        save=True,
    )

    return sell_request.filled_form
