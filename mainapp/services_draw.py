from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

def get_field():
    points = [
        [150, 120],
        [800, 50],
        [1000, 600],
        [900, 700],
        [300, 750],
    ]
    return points


def get_grid(field, step):
    grid = []
    min_x = min((p[0] for p in field))
    min_y = min((p[1] for p in field))
    max_x = max((p[0] for p in field))
    max_y = max((p[1] for p in field))
    polygon = Polygon(field)

    for x in range(min_x, max_x, step):
        for y in range(min_y, max_y, step):
            point = Point(x, y)
            if polygon.contains(point):
                grid.append([x, y])
    return grid


def get_drones_initial_positions(field, grid):
    return [
        [100, 100],
        [1000, 700],
    ]


def get_waypoints(field, grid, drones_inits):
    print(grid)
    return [
        [
            [150, 120],
            [800, 50],
            [200, 200],
            [900, 800],
            [300, 350],
        ],
        grid
    ]
