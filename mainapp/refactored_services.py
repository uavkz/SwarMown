import numpy as np


class Drone(object):
    """
    Drone class, describes all meta and functionality, of UAV
    """

    def __init__(self, weight, speed, battery, ):
        self.weight = weight
        self.speed = speed
        self.battery = battery


class Waypoint(object):
    """
    Waypoint class, with euclidean distance counting method.
    Waypoint is a granular part of route
    Waypoints come from final_path_calculations method, which converts basic x, y coordinates to Waypoint objects
    """

    def __init__(self, x, y, height=3, speed=30, spraying_status=True, landing_status=False):
        self.x = x
        self.y = y
        self.height = height
        self.speed = speed
        self.spraying_status = spraying_status
        self.landing_status = landing_status

    def __str__(self):
        return f'{self.x} - {self.y}'

    def distance(self, other):
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


class Area(object):
    """
    Area class, gets perimeter coordinates and step between coordinate dots.
    Class, can calculate grid and zamboni points
    Got 7 service methods,
    """
    def __init__(self, perimeter, step):

        self.perimeter = perimeter
        self.step = step

        def get_grid():
            """
            returns grid
            """
            from shapely.geometry import Point
            from shapely.geometry.polygon import Polygon

            min_x, max_x = min(self.perimeter, key=lambda x: x[0])[0], max(self.perimeter, key=lambda x: x[0])[0]
            min_y, max_y = min(self.perimeter, key=lambda x: x[1])[1], max(self.perimeter, key=lambda x: x[1])[1]
            polygon = Polygon(self.perimeter)
            grid = [[x, y] for x in np.linspace(min_x, max_x, round((max_x - min_x) / self.step)) 
                    for y in np.linspace(min_y, max_y, round((max_y - min_y) / self.step)) 
                    if polygon.contains(Point(x, y))]
            return grid

        def get_zamboni_path(grid):
            """
            returns zamboni path
            """
            x_dim, y_dim = len(set(np.array(grid)[:, 0].tolist())), len(set(np.array(grid)[:, 1].tolist()))
            zr = np.meshgrid(np.linspace(self.x_min, self.x_max, x_dim),
                             np.linspace(self.y_min, self.y_max, y_dim))
            new_coords = list()
            counter = 0
            for i in range(y_dim):
                for j in range(x_dim):
                    for g in range(len(grid)):
                        if i % 2 == 0:
                            nj = j
                        else:
                            nj = x_dim - j - 1
                        if (grid[g][0] == zr[0][i][nj]) and (grid[g][1] == zr[1][i][nj]):
                            coord = [zr[0][i][nj], zr[1][i][nj]]
                            new_coords.append(coord)
                        counter += 1
            return new_coords

        self.grid = get_grid()
        self.x_max = max(np.array(self.grid)[:, 0])
        self.x_min = min(np.array(self.grid)[:, 0])
        self.y_max = max(np.array(self.grid)[:, 1])
        self.y_min = min(np.array(self.grid)[:, 1])
        self.zamboni_path = get_zamboni_path(grid=self.grid)

    def find_coord(self, to_find):  # REFACTOR
        """
        Finds tuple of coordinates by index
        """
        return self.zamboni_path.index(to_find)

    def get_extreme_points(self):
        """
        Returns dictionary of extremum points
        """
        output = dict()
        output['bottom_left'] = [self.x_min, self.y_min]
        output['top_left'] = [self.x_min, self.y_max]
        output['top_right'] = [self.x_max, self.y_max]
        output['bottom_right'] = [self.x_max, self.y_min]

        return output

    def get_right_edges(self):  # REFACTOR
        """
        Returns coordinates of zamboni right edges
        """
        steps = sorted(set(coord[1] for coord in self.zamboni_path))
        edges = list()
        for step in steps:
            edge_max = 0
            for coord in self.zamboni_path:
                if coord[1] == step and coord[0] > edge_max:
                    edge_max = coord[0]
            edges.append([edge_max, step])
        return edges

    def is_horizontal_grid(self):  # REFACTOR
        """
        returns boolean field type
        """
        from sklearn.metrics.pairwise import haversine_distances
        answer = False
        horizontals = list(filter(lambda x: x[1] == self.y_min, self.grid))
        verts = list(filter(lambda x: x[0] == self.x_min, self.grid))
        hori_min, hori_max = sorted(horizontals)[0], sorted(horizontals)[-1]
        vert_min, vert_max = sorted(verts)[0], sorted(verts)[-1]
        if haversine_distances([hori_min, hori_max])[0][1] > haversine_distances([vert_min, vert_max])[0][1]:
            answer = True
        return answer

    def find_field_edge(self, track_coord):  # REFACTOR
        """
        Calculates right edges of zamboni path, and return edge coordinates, depends on track position
        """
        right_edges = self.get_right_edges()
        distance = list()
        for i in range(len(right_edges)):
            distance.append(euclidean(track_coord[0], right_edges[i][0], track_coord[1], right_edges[i][1]))
        return distance.index(min(distance))

    def total_dist(self, init, final):  # REFACTOR
        """
        Calculates pixel distance between start - end indices of zamboni path
        """
        total_distance_len = 0
        for i in range(len(self.zamboni_path[init:final]) - 1):
            d = euclidean(self.zamboni_path[i][0], self.zamboni_path[i + 1][0],
                          self.zamboni_path[i][1], self.zamboni_path[i + 1][1])
            total_distance_len += d

        return total_distance_len

    def where_to_stop_subfield(self, car_stops):  # REFACTOR
        """
        Service function, returns subfield final index
        """
        edge_ind = self.find_field_edge(car_stops)  # find the coordinate where to stop one pool
        for m in range(len(self.zamboni_path)):
            if right_edges[edge_ind] == list(self.zamboni_path[m]):
                return m

    def __str__(self):
        return f'Area with {len(self.grid)} points'

    def __repr__(self):
        return f'Area with {len(self.grid)} points'
