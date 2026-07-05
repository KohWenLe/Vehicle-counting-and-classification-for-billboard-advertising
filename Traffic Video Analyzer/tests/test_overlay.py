import unittest

try:
    import cv2
    import numpy as np

    from backend.inference.overlay import (
        CLASS_COLORS,
        PENDING_COLOR,
        draw_counting_zone,
        draw_hud,
        draw_track,
        draw_watermark,
    )
except Exception:  # pragma: no cover - cv2/numpy missing
    cv2 = None


def blank_canvas():
    return np.zeros((720, 1280, 3), dtype=np.uint8)


@unittest.skipIf(cv2 is None, "cv2/numpy unavailable")
class OverlayTests(unittest.TestCase):
    def test_resolved_track_draws_class_colored_box_and_chip(self):
        canvas = blank_canvas()

        draw_track(canvas, (200, 200, 400, 350), "High-End Vehicles", confidence=0.82)

        self.assertTrue(canvas.any(), "nothing was drawn")
        expected = np.array(CLASS_COLORS["High-End Vehicles"], dtype=np.uint8)
        matches = (canvas == expected).all(axis=2)
        self.assertGreater(int(matches.sum()), 100, "class color not present on canvas")

    def test_pending_track_draws_thin_gray_box_without_chip(self):
        canvas = blank_canvas()

        draw_track(canvas, (200, 200, 400, 350), "Pending")

        # Anti-aliasing blends edge pixels, so assert "drawn and grayish"
        # rather than exact color: gray has a small max-min channel spread.
        band = canvas[195:355, 195:405]
        drawn = band[band.any(axis=2)]
        self.assertGreater(len(drawn), 50, "pending box not drawn")
        spread = drawn.astype(int).max(axis=1) - drawn.astype(int).min(axis=1)
        self.assertLess(float(spread.mean()), 40.0, "pending box should be gray")
        # No chip: nothing drawn above the box's feathered top edge.
        self.assertFalse(canvas[:196].any(), "pending tracks must not render a label chip")

    def test_chip_anchors_inside_box_near_top_edge(self):
        canvas = blank_canvas()

        # y1=10 is smaller than the chip height, so an above-the-box chip
        # would clip off-frame; it must anchor inside the box instead.
        draw_track(canvas, (200, 10, 400, 150), "Motorcycle")

        self.assertFalse(canvas[:6].any(), "chip clipped off the top of the frame")
        self.assertTrue(canvas[10:150].any())

    def test_counting_zone_fills_polygon_and_keeps_it_translucent(self):
        canvas = blank_canvas()
        canvas[:] = (100, 100, 100)
        polygon = np.array([(400, 300), (900, 300), (900, 600), (400, 600)], dtype=np.int32)

        draw_counting_zone(canvas, polygon)

        inside = canvas[450, 650]
        outside = canvas[100, 100]
        self.assertTrue((inside > outside).all(), "zone interior should be brightened")
        self.assertTrue((inside < 200).all(), "zone fill must stay translucent, not opaque")

    def test_hud_renders_all_class_rows_and_total(self):
        canvas = blank_canvas()
        counts = {label: index for index, label in enumerate(CLASS_COLORS)}
        counts["Unclassified"] = 3

        draw_hud(canvas, counts, "09:15:42", fps=17.6)

        panel = canvas[16:400, 16:316]
        self.assertTrue(panel.any(), "HUD panel not rendered")
        for label, color in CLASS_COLORS.items():
            swatch = (panel == np.array(color, dtype=np.uint8)).all(axis=2)
            self.assertGreater(int(swatch.sum()), 20, f"missing swatch for {label}")

    def test_hud_hides_unclassified_row_when_zero(self):
        counts = {label: 1 for label in CLASS_COLORS}
        with_unclassified = dict(counts, Unclassified=2)
        without_unclassified = dict(counts, Unclassified=0)

        canvas_with = blank_canvas()
        canvas_without = blank_canvas()
        draw_hud(canvas_with, with_unclassified, "09:00:00")
        draw_hud(canvas_without, without_unclassified, "09:00:00")

        rows_with = int(canvas_with[:500, :340].any(axis=2).sum())
        rows_without = int(canvas_without[:500, :340].any(axis=2).sum())
        self.assertGreater(rows_with, rows_without, "panel should shrink when Unclassified is zero")

    def test_watermark_lands_bottom_right(self):
        canvas = blank_canvas()

        draw_watermark(canvas)

        self.assertTrue(canvas[690:715, 1050:1270].any())
        self.assertFalse(canvas[:600].any())


if __name__ == "__main__":
    unittest.main()
