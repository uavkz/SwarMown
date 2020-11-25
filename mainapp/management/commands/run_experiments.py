from django.core.management.base import BaseCommand


class Command(BaseCommand):

    def handle(self, *args, **options):
        self.run()

    def run(self):

        from mainapp.services_draw import get_right_edges, get_zigzag_path, get_field, get_grid, generate_stops, \
            get_extreme_points, when_to_move_forward, best_stop_num, all_pools_flight, final_path_calculations
        import matplotlib.pyplot as plt
        import numpy as np

        field = get_field()
        grid = get_grid(field, 0.0025)
        # from geopy.distance import distance

        MAX_D = 0.15
        SWARM_POPULATION = 3
        DRONE_TIME = 0.05
        TRUCK_SPEED = 30
        extremums = get_extreme_points(grid)
        drones_inits = extremums['bottom_left']
        X_END = extremums['bottom_right'][0]
        Y_END = extremums['top_left'][1]
        zamboni_path = get_zigzag_path(grid=grid)

        right_edges = get_right_edges(new_coords=zamboni_path)

        # First iteration to get the number of flights for each drone in subfields
        truck_path_pool = generate_stops(x_init=drones_inits[0], x_end=X_END,
                                         x_end_km=5, y_const=drones_inits[1], y_init=drones_inits[1],
                                         y_end=Y_END, y_end_km=3,
                                         x_const=drones_inits[0], drone_time=DRONE_TIME,
                                         truck_V=TRUCK_SPEED, grid=grid)

        total_pathways, truck_path = best_stop_num(truck_path_pool=truck_path_pool,
                                                   drone_flight=MAX_D,
                                                   right_edges=right_edges,
                                                   new_coords=zamboni_path)

        pathways_num, pathways, pathways_start_end, pool_endings = all_pools_flight(truck_stops=truck_path,
                                                                                    max_drone_flight=MAX_D,
                                                                                    right_edges=right_edges,
                                                                                    path_coords=zamboni_path)

        drone_lifes = when_to_move_forward(truck_path=truck_path, given_drone_num=SWARM_POPULATION,
                                           estim_pathes=pathways_num)
        final_pathes = final_path_calculations(drone_lifes=drone_lifes, path_coords=zamboni_path,
                                               pool_endings=pool_endings, max_drone_flight=MAX_D)

        waypoints = final_pathes.copy()
        for key, value in final_pathes.items():
            new_path = list()
            for row in value:
                for elem in row:
                    if isinstance(elem, list):
                        new_path.append(elem)
                    else:
                        for sub_elem in elem:
                            new_path.append(list(sub_elem))
            waypoints[key] = new_path

        plt.figure(figsize=(20, 10))
        plt.grid()
        for key, value in waypoints.items():
            to_draw = list()
            for way in value:
                if len(way) > 2:
                    to_draw.extend(way)
                else:
                    to_draw.append(way)
            to_draw = np.array(to_draw)
            plt.plot(to_draw[:, 0], to_draw[:, 1], label=f'drone_{key}')
        plt.legend(loc=4)
        print('!!! check picture window')
        plt.show()
