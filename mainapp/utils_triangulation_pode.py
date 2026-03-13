from gon.base import EMPTY, Multipolygon, Polygon, Triangulation

from pode import Requirement, divide


def remove_overlaps(
    original_polygon: Polygon,
    partitions: list[Polygon],
) -> list[Polygon]:
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


def divide_polygon_with_holes(
    polygon_with_holes: Polygon,
    requirements: list[Requirement],
    verbose: bool = False,
) -> list[Polygon]:
    convex_divisor = Triangulation.constrained_delaunay

    parts = divide(
        polygon_with_holes,
        requirements,
        convex_divisor=convex_divisor,
    )
    if verbose:
        for i, part in enumerate(parts, start=1):
            print(f"Partition {i}:")
            print(f"Area: {float(part.area)}")
            anchor_point = requirements[i - 1].point
            contains_anchor = anchor_point in part if anchor_point else "N/A"
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

    cleaned_parts = remove_overlaps(polygon_with_holes, parts)
    if verbose:
        # Compute area again
        original_area = polygon_with_holes.area
        parts_areas = [part.area for part in cleaned_parts]
        total_parts_area = sum(parts_areas)
        area_difference = original_area - total_parts_area

        print(f"Original polygon area: {float(original_area)}")
        print(f"Total area of partitions: {float(total_parts_area)}")
        print(f"Difference in area: {float(area_difference)}")
    return cleaned_parts
