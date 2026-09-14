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


def _find_table_row_band(horizontal_lines, tolerance=0.35):
    """
    Among all detected horizontal lines, find 7 consecutive ones matching
    this table's shape: one tall gap (header) then 5 roughly-equal gaps
    (data rows). Returns (header_bottom_and_row_boundaries) — a list of
    6 y-values bounding the 5 data rows — or None if no match found.
    """
    lines = sorted(horizontal_lines)
    n = len(lines)

    best = None
    best_score = None

    for start in range(n - 6):
        window = lines[start:start + 7]
        gaps = [window[i + 1] - window[i] for i in range(6)]
        header_gap = gaps[0]
        row_gaps = gaps[1:]
        avg_row = np.mean(row_gaps)

        if avg_row <= 0:
            continue
        # header should be noticeably taller than a data row (wrapped text)
        if header_gap < avg_row * 1.3:
            continue
        # the 5 row gaps should be roughly equal
        deviation = max(abs(g - avg_row) / avg_row for g in row_gaps)
        if deviation > tolerance:
            continue

        score = deviation  # lower is better
        if best_score is None or score < best_score:
            best_score = score
            best = window[1:]  # the 6 boundaries around the 5 data rows

    return best


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
    row_band = _find_table_row_band(h_lines) if len(h_lines) >= 7 else None

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
