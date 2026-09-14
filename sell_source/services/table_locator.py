"""
Locates the middle table's actual printed grid lines on a scanned DSRS
sale request form — DYNAMICALLY, per upload — instead of relying on
fixed pixel/fraction coordinates measured from one example scan.

WHY THIS EXISTS: a different scan of the same physical form will have a
different resolution, crop, and slight rotation each time (phone camera
+ CamScanner). Fixed coordinates drift. This module instead finds the
table's own printed lines using classical computer vision (OpenCV
morphological line detection) — no machine-learning model involved or
needed; a ruled table with straight printed lines is a deterministic
geometry problem, not a learning problem.

APPROACH (validated against a real scan — see conversation for the
step-by-step verification):
  1. Binarize the image (adaptive threshold, tolerant of uneven scan
     lighting).
  2. Detect HORIZONTAL lines within a broad vertical search window
     (roughly where this table lives on the page) using a wide
     morphological opening kernel — this only keeps genuinely long,
     straight horizontal runs, which naturally rejects handwriting,
     stray marks, and noise.
  3. Among the detected horizontal lines, find the specific pattern
     this table has: one unusually TALL gap (the wrapped-text header
     row) followed by 5 roughly EQUAL smaller gaps (the 5 data rows).
  4. Detect VERTICAL lines the same way, scoped to just that row band
     (so lines from other tables on the page don't interfere), and take
     the first 7 from the left edge — the template's column order
     (remarks, serial, activity, mfg_date, physical, nuclide, ردیف) is
     fixed even though exact pixel positions vary scan to scan.

FALLBACK: if detection doesn't find a clean match (e.g. a badly lit or
very different scan), falls back to fixed fractions calibrated from the
reference scan, and flags `used_fallback=True` in the result so calling
code can log/warn rather than silently mis-place text.
"""

import cv2
import numpy as np


# Reference fallback coordinates (fractions of width/height), calibrated
# against the one example scan — only used if dynamic detection fails.
FALLBACK_COLUMNS = {
    "remarks": (0.0542, 0.2887),
    "serial": (0.2892, 0.3411),
    "activity": (0.3416, 0.5160),
    "mfg_date": (0.5164, 0.5993),
    "physical": (0.5998, 0.7373),
    "nuclide": (0.7373, 0.8452),
}
FALLBACK_ROWS = [
    (0.4611, 0.4864),
    (0.4864, 0.5031),
    (0.5031, 0.5197),
    (0.5197, 0.5367),
    (0.5367, 0.5536),
]

# Column keys in template order, LEFT to RIGHT on the page (Persian
# reads right-to-left, so "remarks" — ملاحظات — is visually leftmost).
COLUMN_ORDER = ["remarks", "serial", "activity", "mfg_date", "physical", "nuclide"]

EXPECTED_DATA_ROWS = 5


def _cluster_positions(indices, gap=5):
    """Collapses consecutive/near-consecutive pixel indices (e.g. [100,101,102,150,151])
    into single averaged positions (e.g. [101, 150.5])."""
    if not indices:
        return []
    clusters = [[indices[0]]]
    for i in indices[1:]:
        if i - clusters[-1][-1] <= gap:
            clusters[-1].append(i)
        else:
            clusters.append([i])
    return [int(np.mean(c)) for c in clusters]


def _detect_horizontal_lines(bw, y0, y1, kernel_width_frac=0.15, min_line_width_frac=0.14):
    """
    min_line_width_frac is an ABSOLUTE fraction of the full image width,
    not relative to the strongest line found in this window — using a
    relative threshold breaks when the search window is widened enough
    to include a much stronger, unrelated line elsewhere on the page
    (e.g. a big section border), which silently masks the real (but
    comparatively fainter) internal grid lines this table actually has.
    """
    W = bw.shape[1]
    band = bw[y0:y1, :]
    kw = max(int(W * kernel_width_frac), 10)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kw, 1))
    opened = cv2.morphologyEx(band, cv2.MORPH_OPEN, kernel)
    row_strength = opened.sum(axis=1) / 255.0
    threshold = W * min_line_width_frac
    idx = [y for y in range(len(row_strength)) if row_strength[y] > threshold]
    return [y + y0 for y in _cluster_positions(idx)]


def _detect_vertical_lines(bw, x0, x1, y0, y1, kernel_height_frac=0.25, strength_frac=0.3):
    band = bw[y0:y1, x0:x1]
    kh = max(int((y1 - y0) * kernel_height_frac), 10)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kh))
    opened = cv2.morphologyEx(band, cv2.MORPH_OPEN, kernel)
    col_strength = opened.sum(axis=0) / 255.0
    if col_strength.max() == 0:
        return []
    threshold = max(col_strength.max() * strength_frac, 15)
    idx = [x for x in range(len(col_strength)) if col_strength[x] > threshold]
    return [x + x0 for x in _cluster_positions(idx)]


def _row_darkness(bw, x0, x1, y0, y1):
    """Mean fraction of dark pixels in a band — used to tell a
    text-dense header row apart from a lightly-filled data row."""
    band = bw[y0:y1, x0:x1]
    if band.size == 0:
        return 0.0
    return float((band > 0).mean())


def _shift_and_extrapolate(window):
    """
    Drops one extra line from the front (per observed real-world
    behavior: the line immediately after the header still lands on
    label text, so the true header/row1 boundary is one line further
    than assumed) and extrapolates a 5th row at the end using the
    average row height, so we still return 5 usable rows.
    """
    avg_gap = (window[6] - window[2]) / 4
    extra = int(window[6] + avg_gap)
    return [window[2], window[3], window[4], window[5], window[6], extra]


def _find_table_row_band(horizontal_lines, bw=None, table_x_range=None, tolerance=0.35):
    """
    Among all detected horizontal lines, find 7 consecutive ones matching
    this table's shape: one tall gap (header) then 5 roughly-equal gaps
    (data rows). Returns 6 y-values bounding the 5 data rows, or None.

    If `bw` (the binarized image) and `table_x_range` are given, also
    requires the header candidate to be noticeably more text-dense than
    the rows after it — a wrapped multi-word Persian header across 6
    columns is far denser than a data row (which starts near-blank).
    Without this check, a false "tall gap" elsewhere (e.g. the header
    border missing from the detected line set, causing the window to
    shift by one row) can get accepted, which fills data starting in the
    label row instead of the first real row.
    """
    lines = sorted(horizontal_lines)
    n = len(lines)

    candidates = []

    for start in range(n - 6):
        window = lines[start:start + 7]
        gaps = [window[i + 1] - window[i] for i in range(6)]
        header_gap = gaps[0]
        row_gaps = gaps[1:]
        avg_row = np.mean(row_gaps)

        if avg_row <= 0:
            continue
        if header_gap < avg_row * 1.3:
            continue
        deviation = max(abs(g - avg_row) / avg_row for g in row_gaps)
        if deviation > tolerance:
            continue

        candidates.append((deviation, window))

    candidates.sort(key=lambda c: c[0])

    if bw is None or table_x_range is None:
        return _shift_and_extrapolate(candidates[0][1]) if candidates else None

    x0, x1 = table_x_range
    for deviation, window in candidates:
        header_density = _row_darkness(bw, x0, x1, window[0], window[1])
        row_densities = [
            _row_darkness(bw, x0, x1, window[i], window[i + 1])
            for i in range(1, 6)
        ]
        avg_row_density = np.mean(row_densities) if row_densities else 0
        # Header (wrapped, multi-word, 6 columns of Persian text) should
        # be substantially denser than an average data row.
        if header_density > avg_row_density * 1.8 and header_density > 0.03:
            return _shift_and_extrapolate(window)

    # No candidate passed the density check — fall back to the
    # best-fitting shape match rather than giving up entirely, but this
    # case is exactly the one worth logging/flagging upstream.
    return _shift_and_extrapolate(candidates[0][1]) if candidates else None


def locate_table(image_bgr):
    """
    Returns:
        {
            "rows": [(y0,y1), ...] * 5,      # absolute pixel y-ranges
            "columns": {key: (x0,x1), ...},  # absolute pixel x-ranges
            "used_fallback": bool,
        }
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15)

    # Broad search window — this table lives roughly in the lower-middle
    # of the page; wide enough to tolerate scan-to-scan crop variance.
    search_y0, search_y1 = int(0.30 * H), int(0.75 * H)

    h_lines = _detect_horizontal_lines(bw, search_y0, search_y1)
    row_band = (
        _find_table_row_band(h_lines, bw=bw, table_x_range=(0, W))
        if len(h_lines) >= 7 else None
    )

    if row_band is None:
        # Fallback to fixed fractions.
        rows_px = [(int(y0f * H), int(y1f * H)) for y0f, y1f in FALLBACK_ROWS]
        columns_px = {
            key: (int(x0f * W), int(x1f * W))
            for key, (x0f, x1f) in FALLBACK_COLUMNS.items()
        }
        return {"rows": rows_px, "columns": columns_px, "used_fallback": True}

    rows_px = [(row_band[i], row_band[i + 1]) for i in range(5)]

    table_top, table_bottom = row_band[0], row_band[-1]
    v_lines = _detect_vertical_lines(bw, 0, W, table_top, table_bottom)

    if len(v_lines) < 7:
        columns_px = {
            key: (int(x0f * W), int(x1f * W))
            for key, (x0f, x1f) in FALLBACK_COLUMNS.items()
        }
        return {"rows": rows_px, "columns": columns_px, "used_fallback": True}

    v_lines = sorted(v_lines)[:7]  # left border + 6 internal boundaries we need
    columns_px = {
        COLUMN_ORDER[i]: (v_lines[i], v_lines[i + 1])
        for i in range(6)
    }

    return {"rows": rows_px, "columns": columns_px, "used_fallback": False}