import unittest

try:
    from gon.base import Contour, Point, Polygon

    from mainapp.utils_triangulation_pode import (
        divide_polygon_with_holes,
        remove_overlaps,
    )
    from pode import Requirement

    PODE_AVAILABLE = True
except ImportError:
    PODE_AVAILABLE = False


@unittest.skipUnless(PODE_AVAILABLE, "pode / gon packages not installed")
class DividePolygonWithHolesTests(unittest.TestCase):
    """Tests for divide_polygon_with_holes() and remove_overlaps()."""

    def setUp(self):
        # Square with a small square hole
        self.outer = Contour([Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)])
        self.hole = Contour([Point(3, 3), Point(5, 3), Point(5, 5), Point(3, 5)])
        self.polygon = Polygon(self.outer, [self.hole])
        self.reqs = [Requirement(0.5), Requirement(0.5)]

    # 1. Smoke test
    def test_smoke_divide_polygon(self):
        """divide_polygon_with_holes returns a list for a simple polygon with one hole."""
        parts = divide_polygon_with_holes(self.polygon, self.reqs)
        self.assertIsInstance(parts, list)
        self.assertGreater(len(parts), 0)

    # 2. Number of partitions
    def test_number_of_partitions(self):
        """Returns the correct number of sub-polygons matching requirements."""
        parts = divide_polygon_with_holes(self.polygon, self.reqs)
        self.assertEqual(len(parts), len(self.reqs))

    # 3. Coverage - sum of partition areas approximately equals original area
    def test_coverage_area(self):
        """Sum of partition areas approximately equals the original polygon area (within 1%)."""
        parts = divide_polygon_with_holes(self.polygon, self.reqs)
        original_area = float(self.polygon.area)
        total_parts_area = sum(float(p.area) for p in parts)
        self.assertAlmostEqual(
            total_parts_area,
            original_area,
            delta=original_area * 0.01,
            msg=(f"Total parts area {total_parts_area} differs from original area {original_area} by more than 1%"),
        )

    # 4. remove_overlaps - cleaned version has no overlap
    def test_remove_overlaps_no_overlap(self):
        """After remove_overlaps, partitions do not overlap (areas sum to original)."""
        # Create two overlapping polygons that both cover parts of the outer square
        poly_a = Polygon(Contour([Point(0, 0), Point(6, 0), Point(6, 10), Point(0, 10)]))
        poly_b = Polygon(Contour([Point(4, 0), Point(10, 0), Point(10, 10), Point(4, 10)]))
        original = Polygon(self.outer)
        cleaned = remove_overlaps(original, [poly_a, poly_b])
        total_cleaned_area = sum(float(p.area) for p in cleaned)
        original_area = float(original.area)
        self.assertAlmostEqual(
            total_cleaned_area,
            original_area,
            delta=original_area * 0.01,
            msg="Cleaned partitions should cover the original polygon without overlap",
        )

    # 5. Simple polygon without holes - divide a square with 2 Requirements
    def test_simple_polygon_no_holes(self):
        """Dividing a simple square (no holes) with 2 Requirements returns 2 parts."""
        simple_square = Polygon(self.outer)
        reqs = [Requirement(0.5), Requirement(0.5)]
        parts = divide_polygon_with_holes(simple_square, reqs)
        self.assertEqual(len(parts), len(reqs))
