"""Commercial-style overlay rendering for the annotated output video.

Pure drawing functions over a BGR canvas: per-class colored boxes, filled
label chips with luminance-picked text, a translucent counting zone, and a
semi-transparent HUD panel with per-class counts, timestamp, and processing
FPS. All primitives are anti-aliased. No pipeline state lives here, so the
module is unit-testable on synthetic frames.
"""

import cv2
import numpy as np


# BGR palette (hex reference in comments).
CLASS_COLORS = {
    "Commercial Vehicles": (11, 158, 245),  # #F59E0B amber
    "High-End Vehicles": (247, 85, 168),    # #A855F7 violet
    "Mid-Range Vehicles": (246, 130, 59),   # #3B82F6 blue
    "Low-End Vehicles": (129, 185, 16),     # #10B981 emerald
    "Motorcycle": (68, 68, 239),            # #EF4444 red
}
PENDING_COLOR = (175, 163, 156)             # #9CA3AF gray
UNCLASSIFIED_COLOR = PENDING_COLOR

SHORT_LABELS = {
    "Commercial Vehicles": "Commercial",
    "High-End Vehicles": "High-End",
    "Low-End Vehicles": "Low-End",
    "Mid-Range Vehicles": "Mid-Range",
    "Motorcycle": "Motorcycle",
    "Unclassified": "Unclassified",
}

_FONT = cv2.FONT_HERSHEY_DUPLEX
_PANEL_BG = (42, 23, 15)        # #0F172A slate-900
_PANEL_BORDER = (85, 65, 51)    # #334155
_TITLE_COLOR = (240, 232, 226)  # #E2E8F0
_SUBTLE_COLOR = (184, 163, 148)  # #94A3B8
_ROW_COLOR = (225, 213, 203)    # #CBD5E1
_ZONE_COLOR = (235, 231, 229)   # #E5E7EB
_WATERMARK_COLOR = (139, 116, 100)  # #64748B
_DARK_TEXT = (17, 17, 17)       # #111111


def _text_color_for(background_bgr):
    b, g, r = background_bgr
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    return (255, 255, 255) if luma < 140 else _DARK_TEXT


def _blend_rect(canvas, pt1, pt2, color, alpha):
    """Alpha-blend a filled rectangle onto the canvas in place."""
    height, width = canvas.shape[:2]
    x1, y1 = max(0, pt1[0]), max(0, pt1[1])
    x2, y2 = min(width, pt2[0]), min(height, pt2[1])
    if x2 <= x1 or y2 <= y1:
        return
    region = canvas[y1:y2, x1:x2]
    fill = np.full_like(region, color)
    cv2.addWeighted(fill, alpha, region, 1.0 - alpha, 0, dst=region)


def draw_track(canvas, box, label, confidence=None, track_id=None, show_track_id=False):
    """Draw one counted track. `label` is "Pending" or a resolved class label.

    Pending tracks get a thin gray box with no text; resolved tracks get a
    2px class-colored box and a filled label chip.
    """
    x1, y1, x2, y2 = box
    if label == "Pending":
        cv2.rectangle(canvas, (x1, y1), (x2, y2), PENDING_COLOR, 1, lineType=cv2.LINE_AA)
        return

    color = CLASS_COLORS.get(label, UNCLASSIFIED_COLOR)
    cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2, lineType=cv2.LINE_AA)

    text = SHORT_LABELS.get(label, label)
    if confidence is not None:
        text = f"{text} {confidence:.2f}"
    if show_track_id and track_id is not None:
        text = f"{text} #{track_id}"

    (text_w, text_h), baseline = cv2.getTextSize(text, _FONT, 0.5, 1)
    chip_w = text_w + 12
    chip_h = text_h + baseline + 8
    chip_x = max(0, min(x1, canvas.shape[1] - chip_w))
    chip_y = y1 - chip_h
    if chip_y < 0:
        chip_y = y1 + 2  # anchor inside the box when it would clip off-frame
    _blend_rect(canvas, (chip_x, chip_y), (chip_x + chip_w, chip_y + chip_h), color, 0.85)
    cv2.putText(
        canvas,
        text,
        (chip_x + 6, chip_y + chip_h - baseline - 3),
        _FONT,
        0.5,
        _text_color_for(color),
        1,
        lineType=cv2.LINE_AA,
    )


def draw_counting_zone(canvas, polygon):
    """Render the counting ROI as a subtle filled zone with an AA border."""
    overlay_fill = np.zeros_like(canvas)
    cv2.fillPoly(overlay_fill, [polygon], _ZONE_COLOR)
    mask = overlay_fill.any(axis=2)
    region = canvas[mask]
    canvas[mask] = (0.88 * region + 0.12 * np.array(_ZONE_COLOR)).astype(canvas.dtype)
    cv2.polylines(canvas, [polygon], isClosed=True, color=_ZONE_COLOR, thickness=2, lineType=cv2.LINE_AA)

    tag_anchor = polygon.min(axis=0)
    cv2.putText(
        canvas,
        "COUNTING ZONE",
        (int(tag_anchor[0]) + 6, int(tag_anchor[1]) + 18),
        _FONT,
        0.4,
        _ZONE_COLOR,
        1,
        lineType=cv2.LINE_AA,
    )


def draw_hud(canvas, class_counts, timestamp_text, fps=None):
    """Top-left translucent panel: title, timestamp/FPS, per-class rows, total."""
    panel_x, panel_y = 16, 16
    panel_w = 300
    row_h = 24
    class_rows = [label for label in CLASS_COLORS if label in class_counts]
    unclassified = class_counts.get("Unclassified", 0)
    extra_rows = 1 if unclassified > 0 else 0
    panel_h = 30 + 22 + 8 + (len(class_rows) + extra_rows) * row_h + 8 + 28

    # 0.75 keeps the translucent look but stops bright vehicles underneath
    # from washing out the counts.
    _blend_rect(canvas, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), _PANEL_BG, 0.75)
    cv2.rectangle(
        canvas,
        (panel_x, panel_y),
        (panel_x + panel_w, panel_y + panel_h),
        _PANEL_BORDER,
        1,
        lineType=cv2.LINE_AA,
    )

    cursor_y = panel_y + 24
    cv2.putText(canvas, "TRAFFIC ANALYZER", (panel_x + 12, cursor_y), _FONT, 0.55, _TITLE_COLOR, 1, lineType=cv2.LINE_AA)

    cursor_y += 22
    sub_text = timestamp_text if fps is None else f"{timestamp_text}   {fps:.1f} FPS"
    cv2.putText(canvas, sub_text, (panel_x + 12, cursor_y), _FONT, 0.45, _SUBTLE_COLOR, 1, lineType=cv2.LINE_AA)

    cursor_y += 8
    cv2.line(canvas, (panel_x + 12, cursor_y), (panel_x + panel_w - 12, cursor_y), _PANEL_BORDER, 1, lineType=cv2.LINE_AA)

    for label in class_rows:
        cursor_y += row_h
        swatch_y = cursor_y - 11
        cv2.rectangle(
            canvas,
            (panel_x + 12, swatch_y),
            (panel_x + 24, swatch_y + 12),
            CLASS_COLORS[label],
            -1,
            lineType=cv2.LINE_AA,
        )
        cv2.putText(canvas, SHORT_LABELS[label], (panel_x + 32, cursor_y), _FONT, 0.5, _ROW_COLOR, 1, lineType=cv2.LINE_AA)
        count_text = str(class_counts[label])
        (count_w, _), _ = cv2.getTextSize(count_text, _FONT, 0.5, 1)
        cv2.putText(canvas, count_text, (panel_x + panel_w - 12 - count_w, cursor_y), _FONT, 0.5, (255, 255, 255), 1, lineType=cv2.LINE_AA)

    if unclassified > 0:
        cursor_y += row_h
        cv2.putText(canvas, "Unclassified", (panel_x + 32, cursor_y), _FONT, 0.5, _SUBTLE_COLOR, 1, lineType=cv2.LINE_AA)
        count_text = str(unclassified)
        (count_w, _), _ = cv2.getTextSize(count_text, _FONT, 0.5, 1)
        cv2.putText(canvas, count_text, (panel_x + panel_w - 12 - count_w, cursor_y), _FONT, 0.5, _SUBTLE_COLOR, 1, lineType=cv2.LINE_AA)

    cursor_y += 12
    cv2.line(canvas, (panel_x + 12, cursor_y), (panel_x + panel_w - 12, cursor_y), _PANEL_BORDER, 1, lineType=cv2.LINE_AA)
    cursor_y += 22
    cv2.putText(canvas, "TOTAL", (panel_x + 12, cursor_y), _FONT, 0.5, (255, 255, 255), 2, lineType=cv2.LINE_AA)
    total_text = str(sum(class_counts.values()))
    (total_w, _), _ = cv2.getTextSize(total_text, _FONT, 0.5, 2)
    cv2.putText(canvas, total_text, (panel_x + panel_w - 12 - total_w, cursor_y), _FONT, 0.5, (255, 255, 255), 2, lineType=cv2.LINE_AA)


def draw_watermark(canvas, text="Traffic Video Analyzer"):
    (text_w, text_h), _ = cv2.getTextSize(text, _FONT, 0.4, 1)
    height, width = canvas.shape[:2]
    cv2.putText(
        canvas,
        text,
        (width - text_w - 14, height - 14),
        _FONT,
        0.4,
        _WATERMARK_COLOR,
        1,
        lineType=cv2.LINE_AA,
    )
