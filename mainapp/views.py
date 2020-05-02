from django.views.generic import TemplateView

from mainapp.services_draw import *
from mainapp.ga_services import *
from mainapp.kinematic_constants import *


class MownView(TemplateView):
    template_name = "mainapp/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        field = get_field()
        grid = get_grid(field, 50)
        initial_position = get_initial_position(field, grid)
        number_of_drones = 2
        waypoints = get_waypoints(field, grid, initial_position)
        context['field'] = [coord for point in field for coord in point]
        context['grid'] = grid
        context['initial'] = initial_position
        context['waypoints'] = [[initial_position] + w + [initial_position] for w in waypoints]
        context['number_of_drones'] = number_of_drones
        return context


class GaView(TemplateView):
    template_name = "mainapp/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        field = get_field()
        grid = get_grid(field, 50)
        waypoints = generate_waypoints(grid)
        initial_position = generate_car_position()
        number_of_drones = len(waypoints)
        context['field'] = [coord for point in field for coord in point]
        context['grid'] = grid
        context['initial'] = initial_position
        context['waypoints'] = waypoints
        context['number_of_drones'] = number_of_drones
        return context


class ZamboniView(TemplateView):
    template_name = "mainapp/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        field = get_field()
        grid = get_grid(field, 50)
        initial_position = TRACK_COORD
        number_of_drones, waypoints, coords = drones_num(TRACK_COORD, MAX_D, INIT_P, PERCENT, grid)
        context['field'] = [coord for point in field for coord in point]
        context['grid'] = grid
        context['initial'] = initial_position
        context['waypoints'] = waypoints
        context['number_of_drones'] = SWARM_POPULATION
        return context
