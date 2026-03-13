"""Monkey patches for third-party libraries (gon/pode)."""

from collections.abc import Sequence
from itertools import chain


def _patched_polygon_edges(self) -> Sequence:
    """Patched Polygon.edges that handles ground.core Contour/Point types.

    The gon library sometimes returns ground.core types instead of gon.base
    types for contour vertices, causing attribute errors. This patch converts
    them on the fly.
    """
    from gon.base import Contour as GonContour
    from gon.base import Point as GonPoint
    from ground.core.hints import Contour as GroundContour
    from ground.core.hints import Point as GroundPoint

    def ground_point_to_gon_point(ground_point: GroundPoint) -> GonPoint:
        return GonPoint(ground_point.x, ground_point.y)

    def ground_contour_to_gon_contour(ground_contour: GroundContour) -> GonContour:
        return GonContour([ground_point_to_gon_point(v) for v in ground_contour.vertices])

    if isinstance(self.border, GroundContour):
        self._border = ground_contour_to_gon_contour(self.border)

    flatten = chain.from_iterable
    return list(chain(self.border.segments, flatten(hole.segments for hole in self.holes)))


def apply_patches():
    """Apply all monkey patches. Call once during app startup."""
    try:
        from gon.core.polygon import Polygon

        Polygon.edges = property(_patched_polygon_edges)
    except ImportError:
        pass
