from django.views.generic import TemplateView

from mainapp.services_draw import get_field


class MownView(TemplateView):
    template_name = "mainapp/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['field'] = get_field()
        return context
