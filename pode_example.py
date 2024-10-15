from pode import divide, Requirement
from gon.base import Point, Polygon, Contour

outer_boundary = Contour([Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)])
hole1 = Contour([Point(2, 2), Point(4, 2), Point(4, 4), Point(2, 4)])
hole2 = Contour([Point(6, 6), Point(8, 6), Point(8, 8), Point(6, 8)])

polygon_with_holes = Polygon(outer_boundary, [hole1, hole2])

requirements = [
    Requirement(0.3),  # 50% of the area, no anchor point
    Requirement(0.3),  # 50% of the area, no anchor point
    Requirement(0.3),  # 50% of the area, no anchor point
    Requirement(1 - (0.3) * 3),  # 50% of the area, no anchor point
    # Requirement(1/6),  # 50% of the area, no anchor point
    # Requirement(1/6),  # 50% of the area, no anchor point
    # Requirement(1/6),  # 50% of the area, no anchor point
    # Requirement(1/6),  # 50% of the area, no anchor point
    # Requirement(1/6),  # 50% of the area, no anchor point
    # Requirement(1 - (1/6) * 5),  # 50% of the area, no anchor point
]

from gon.base import Triangulation
# Each parameter is triangle.
convex_divisor = Triangulation.constrained_delaunay

parts = divide(
    polygon_with_holes,
    requirements,
    convex_divisor=convex_divisor,
)

for i, part in enumerate(parts, start=1):
    print(f"Partition {i}:")
    print(f"Area: {float(part.area)}")
    anchor_point = requirements[i - 1].point
    contains_anchor = anchor_point in part if anchor_point else 'N/A'
    print(f"Contains anchor point: {contains_anchor}")
    print(f"Coordinates: {part.border.vertices}\n")



####### There can be overlaps :/
original_area = polygon_with_holes.area
parts_areas = [part.area for part in parts]
total_parts_area = sum(parts_areas)
area_difference = original_area - total_parts_area

print(f"Original polygon area: {float(original_area)}")
print(f"Total area of partitions: {float(total_parts_area)}")
print(f"Difference in area: {float(area_difference)}")


# Fix overlaps
from gon.base import EMPTY, Multipolygon

def remove_overlaps(original_polygon, partitions):
    """
    Removes overlapping areas from partitions to ensure that:
    - All partitions are mutually exclusive (no overlaps).
    - The union of all partitions equals the original polygon.

    Parameters:
    - original_polygon (Polygon): The original polygon to be partitioned.
    - partitions (List[Polygon]): The list of partitioned polygons which may have overlaps.

    Returns:
    - cleaned_partitions (List[Polygon]): The list of partitions without overlaps, covering the original polygon.
    """
    cleaned_partitions = []
    covered_area = EMPTY
    for part in partitions:
        # Subtract the already covered area to get the non-overlapping part
        non_overlapping = part - covered_area
        if non_overlapping != EMPTY:
            cleaned_partitions.append(non_overlapping)
            # Update the covered area
            covered_area |= non_overlapping
    # Identify any missing areas that weren't covered by the partitions
    missing_area = original_polygon - covered_area
    if missing_area != EMPTY:
        if isinstance(missing_area, Polygon):
            cleaned_partitions.append(missing_area)
        elif isinstance(missing_area, Multipolygon):
            cleaned_partitions.extend(missing_area.polygons)
        else:
            # Handle other geometry types if necessary
            pass
    return cleaned_partitions

cleaned_parts = remove_overlaps(polygon_with_holes, parts)

# Compute area again
original_area = polygon_with_holes.area
parts_areas = [part.area for part in cleaned_parts]
total_parts_area = sum(parts_areas)
area_difference = original_area - total_parts_area

print(f"Original polygon area: {float(original_area)}")
print(f"Total area of partitions: {float(total_parts_area)}")
print(f"Difference in area: {float(area_difference)}")


######### VISUALIZE
import matplotlib.pyplot as plt
from gon.base import Multipolygon

multipolygon = Multipolygon(cleaned_parts)

fig, ax = plt.subplots()
for polygon in multipolygon.polygons:
    x, y = zip(*[(p.x, p.y) for p in polygon.border.vertices])
    ax.fill(x, y, alpha=1, edgecolor='black', linewidth=1)
    for hole in polygon.holes:
        xh, yh = zip(*[(p.x, p.y) for p in hole.vertices])
        ax.fill(xh, yh, color='white', edgecolor='black', linewidth=1)

for req in requirements:
    if req.point:
        ax.plot(req.point.x, req.point.y, 'ro')  # Red dot for anchor points

ax.set_aspect('equal')
plt.show()


