from django.views.generic import TemplateView

from mainapp.services_draw import get_field, get_grid


class MownView(TemplateView):
    template_name = "mainapp/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        field = get_field()
        context['field'] = [coord for point in field for coord in point]
        context['grid'] = get_grid(field, 100)
        return context
