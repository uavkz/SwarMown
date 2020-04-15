from django.views.generic import TemplateView

from mainapp.services_draw import *
from mainapp.ga_services import *


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
        waypoints, center_coordinates = generate_waypoints(grid)
        context['field'] = [coord for point in field for coord in point]
        context['grid'] = grid
        context['initial'] = center_coordinates
        context['waypoints'] = waypoints
        context['number_of_drones'] = len(waypoints)
        return context
