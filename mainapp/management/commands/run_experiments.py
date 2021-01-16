from django.core.management.base import BaseCommand


class Command(BaseCommand):

    def handle(self, *args, **options):
        self.run()

    def run(self):

        from mainapp.refactored_services import Area
        from mainapp.to_refactor_services import generate_stops, best_stop_num, all_pools_flight, when_to_move_forward, \
            final_path_calculations
        import matplotlib.pyplot as plt
        import numpy as np

        perimeter = [
            [76.84627532958986, 43.21933865889726],
            [76.84301376342773, 43.23559036068933],
            [76.84816360473634, 43.25096298148861],
            [76.87253952026369, 43.25421198192111],
            [76.88798904418947, 43.23696530585579],
            [76.88781738281251, 43.22296441400881],
            [76.87511444091798, 43.21571268816603],
            [76.86035156250001, 43.21496246040482]
        ]

        step = 0.0025
        field_first = Area(perimeter=perimeter, step=step)
        MAX_D = 0.15
        SWARM_POPULATION = 3
        DRONE_TIME = 0.05
        TRUCK_SPEED = 30
        extremums = field_first.get_extreme_points()
        drones_inits = extremums['bottom_left']
        X_END = extremums['bottom_right'][0]
        Y_END = extremums['top_left'][1]

        # First iteration to get the number of flights for each drone in subfields
        truck_path_pool = generate_stops(x_init=drones_inits[0], x_end=X_END,
                                         x_end_km=5, y_const=drones_inits[1], y_init=drones_inits[1],
                                         y_end=Y_END, y_end_km=3, x_const=drones_inits[0], drone_time=DRONE_TIME,
                                         truck_V=TRUCK_SPEED, direction='horizontal', iters=5)

        total_pathways, truck_path = best_stop_num(truck_path_pool, MAX_D, field_first.get_right_edges(),
                                                   field_first.zamboni_path)

        pathways_num, pathways, pathways_start_end, pool_endings = all_pools_flight(truck_path, MAX_D,
                                                                                    field_first.get_right_edges(),
                                                                                    field_first.zamboni_path)

        drone_lifes = when_to_move_forward(truck_path, SWARM_POPULATION, pathways_num)

        # Final iteration
        final_path = final_path_calculations(drone_lifes, field_first.zamboni_path, pool_endings, MAX_D)

        waypoints = final_path.copy()
        for key, value in final_path.items():
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
