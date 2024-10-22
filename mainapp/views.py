import asyncio
import csv
import json
import zipfile
from io import BytesIO

from django.http import HttpResponseRedirect
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView, ListView

from mainapp.models import *
from mainapp.utils import flatten_grid
from mainapp.service_routing import get_route
from mainapp.utils_gis import get_elevations_for_points_dict
from mainapp.utils_mavlink import create_plan_file


class Index(View):
    def get(self, request, **kwargs):
        return HttpResponseRedirect(reverse_lazy('mainapp:list_mission'))


def get_all_points(context):
    all_points = []
    for waypoints in context['waypoints']:
        for waypoint in waypoints:
            all_points.append([waypoint['lat'], waypoint['lon']])

    return get_elevations_for_points_dict(all_points)


class ManageRouteView(TemplateView):
    template_name = "mainapp/manage_route.html"

    def handle(self, context):
        car_move = self.request.GET.get("carMove", "no")
        direction = self.request.GET.get("direction", "simple")
        start = self.request.GET.get("start", "ne")
        height_diff = self.request.GET.get("heightDiff", False) == "on"
        round_start_zone = self.request.GET.get("roundStartZone", False) == "on"
        feature3 = self.request.GET.get("feature3", False) == "on"
        feature4 = self.request.GET.get("feature4", False) == "on"

        serialized = self.request.GET.get("serialized", False)
        if serialized:
            serialized = json.loads(serialized.replace("'", '"'))

        field_obj = context['mission'].field
        field = json.loads(field_obj.points_serialized)
        field = [[y, x] for (x, y) in field]
        road = json.loads(field_obj.road_serialized)
        road = [[y, x] for (x, y) in road]
        holes = json.loads(field_obj.holes_serialized) # three-dimensional array: [# First hole # [[lat, lon], [lat, lon], ...], # Second hole # [[lat, lon], [lat, lon], ...], ...]
        holes = [[[y, x] for (x, y) in hole] for hole in holes]

        grid_step = context['mission'].grid_step
        number_of_drones = context['mission'].drones.all().count()
        # [x, y, z, is_active]

        context['field_flat'] = [coord for point in field for coord in point]
        context['field_id'] = field_obj.id if field_obj else ""
        context['field'] = field
        context['road'] = road
        context['holes'] = holes
        context['grid_step'] = grid_step
        context['number_of_drones'] = number_of_drones
        if serialized:
            drones = [list(context['mission'].drones.all().order_by('id'))[i] for i in serialized[2]]
            grid, waypoints, car_waypoints, initial_position = get_route(
                car_move=serialized[3],
                direction=serialized[0],
                start=serialized[1],
                field=field,
                holes=holes,
                grid_step=context['mission'].grid_step,
                road=road,
                drones=drones,
            )
        else:
            grid, waypoints, car_waypoints, initial_position = get_route(
                car_move=car_move,
                direction=direction,
                start=start,
                field=field,
                holes=holes,
                grid_step=grid_step,
                road=road,
                drones=context['mission'].drones.all().order_by('id'),
            )
        context['grid'] = list(flatten_grid(grid))
        context['initial'] = initial_position
        context['waypoints'] = waypoints
        # print("!!!")
        # with open(f"{field_obj}.txt", "w") as f:
        #     for w in waypoints[0]:
        #         f.write(f"{w['lat']} {w['lon']}\n")
        context['pickup_waypoints'] = car_waypoints

    def get(self, request, *args, **kwargs):
        if "submitSave" in self.request.GET:
            context = self.get_context_data(**kwargs)
            i = 0
            context['mission'].current_waypoints_status = 1
            context['mission'].save()
            context['mission'].current_waypoints.all().delete()
            for waypoints in context['waypoints']:
                for waypoint in waypoints:
                    w = Waypoint.objects.create(
                        drone_id=waypoint['drone']['id'],
                        index=i,
                        lat=waypoint['lat'],
                        lon=waypoint['lon'],
                        height=waypoint['height'],
                        speed=waypoint['speed'],
                        acceleration=waypoint['acceleration'],
                        spray_on=waypoint['spray_on'],
                    )
                    i += 10
                    context['mission'].current_waypoints.add(w)
            context['mission'].current_waypoints_status = 2
            context['mission'].save()
            return HttpResponseRedirect(reverse_lazy('mainapp:list_mission'))
        if "getCsv" in self.request.GET:
            context = self.get_context_data(**kwargs)
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="waypoints.csv"'
            writer = csv.writer(response)
            writer.writerow(['lat', 'lon', 'height', 'height_global', 'drone_id', 'drone_name', 'drone_model', 'speed', 'acceleration', 'spray_on'])
            elevations_dict = asyncio.run(get_all_points(context))
            for waypoints in context['waypoints']:
                for waypoint in waypoints:
                    height_absolute = request.GET.get(
                        "height_absolute", False
                    )
                    if not height_absolute:
                        height_absolute = elevations_dict[(round(waypoint['lat'], 3)), round(waypoint['lon'], 3)]
                    writer.writerow([
                        waypoint["lat"],
                        waypoint["lon"],
                        height_absolute + float(request.GET.get("height", 450.0)),
                        height_absolute,
                        waypoint["drone"]["id"],
                        waypoint["drone"]["name"], waypoint["drone"]["model"],
                        waypoint["speed"],
                        waypoint["acceleration"],
                        waypoint["spray_on"],
                    ])
                return response
        if "getJson" in self.request.GET:
            context = self.get_context_data(**kwargs)
            data = []
            elevations_dict = asyncio.run(get_all_points(context))
            for waypoints in context['waypoints']:
                for waypoint in waypoints:
                    height_absolute = request.GET.get(
                        "height_absolute", False
                    )
                    if not height_absolute:
                        height_absolute = elevations_dict[(round(waypoint['lat'], 3)), round(waypoint['lon'], 3)]
                    data.append(
                        {
                            "lat": waypoint["lat"],
                            "lon": waypoint["lon"],
                            "height": height_absolute + float(request.GET.get("height", 450.0)),
                            "height_global": height_absolute,
                            "drone_id": waypoint["drone"]["id"],
                            "drone_name": waypoint["drone"]["name"],
                            "drone_model": waypoint["drone"]["model"],
                            "speed": waypoint["speed"],
                            "acceleration": waypoint["acceleration"],
                            "spray_on": waypoint["spray_on"],
                        }
                    )
            drone_ids = list(set([d['drone_id'] for d in data]))
            jsons = [
                create_plan_file([
                    [d['lat'], d['lon'], d['height']]
                    for d in data if d['drone_id'] == drone_id
                ], drone_id)
                for drone_id in drone_ids
            ]
            if len(jsons) == 1:
                response = HttpResponse(json.dumps(jsons[0]), content_type='application/json')
                response['Content-Disposition'] = 'attachment; filename="plan.json"'
            else:
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                    for i, (json_data, drone_id)  in enumerate(zip(jsons, drone_ids)):
                        file_name = f"plan_{drone_id}_{i}.json"
                        zip_file.writestr(file_name, json.dumps(json_data))

                zip_buffer.seek(0)
                response = HttpResponse(zip_buffer, content_type='application/zip')
                response['Content-Disposition'] = 'attachment; filename="plans.zip"'

            return response

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['mission'] = Mission.objects.get(id=kwargs['mission_id'])
        self.handle(context)
        return context


class MissionsCreateView(TemplateView):
    template_name = "mainapp/add_mission.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['types'] = Mission.TYPES
        context['fields'] = Field.objects.all()
        context['drones'] = Drone.objects.all()
        return context

    def post(self, request, **kwargs):
        m = Mission.objects.create(
            name=request.POST['name'],
            description=request.POST['description'],
            type=request.POST['type'],
            field_id=request.POST['field'],
            grid_step=request.POST['grid_step'],
        )
        m.drones.add(*request.POST.getlist('drones'))
        return HttpResponseRedirect(reverse_lazy('mainapp:list_mission'))


class MissionsListView(ListView):
    template_name = "mainapp/list_mission.html"
    queryset = Mission.objects.all().order_by('-id')
