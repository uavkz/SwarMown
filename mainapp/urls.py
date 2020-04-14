from django.urls import path

from .views import *

app_name = 'mainapp'

urlpatterns = [
    path('', MownView.as_view(), name="index"),
    path('genetic/', GaView.as_view(), name='genetic')
]
