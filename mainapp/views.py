import asyncio
import csv
import json
import os
import sys
import zipfile
from io import BytesIO

from django.http import HttpResponseRedirect
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.views.decorators.http import require_http_methods
from django.views.generic import TemplateView, ListView

import xml.etree.ElementTree as ET

from mainapp.models import *
from mainapp.utils import flatten_grid
from mainapp.service_routing import get_route
from mainapp.utils_gis import get_elevations_for_points_dict
from mainapp.utils_mavlink import create_plan_file


import time
import subprocess
import urllib.parse
from django.conf import settings
from django.http import FileResponse
from django.utils.text import slugify



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

    def _pick_python(self):
        candidates = []
        env_py = os.environ.get("GA_PYTHON")
        if env_py:
            candidates.append(env_py)
        try:
            candidates.append(sys.executable)
        except Exception:
            pass
        candidates.append(os.path.join(settings.BASE_DIR, "venv39", "Scripts", "python.exe"))
        candidates.append("python")

        for p in candidates:
            try:
                subprocess.run([p, "-c", "import scoop"], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return p
            except Exception:
                continue
        return candidates[0]

    def _optimize_now(self, mission):
        holes_raw = mission.field.holes_serialized or "[]"
        has_holes = bool(json.loads(holes_raw))
        script_rel = os.path.join("scripts", "genetic_holes.py" if has_holes else "genetic.py")

        ncores = int(self.request.GET.get("cores", 8) or 8)
        ngen = int(self.request.GET.get("ngen", 3) or 5)
        population_size = int(self.request.GET.get("population_size", 30) or 30)
        max_time = float(self.request.GET.get("max_time", 8) or 8)
        borderline_time = float(self.request.GET.get("borderline_time", 2) or 2)
        max_working_speed = float(self.request.GET.get("max_working_speed", 7) or 7)
        mutation_chance = float(self.request.GET.get("mutation_chance", 0.1) or 0.1)

        out_dir = os.path.join(settings.MEDIA_ROOT, "opt_results")
        os.makedirs(out_dir, exist_ok=True)
        base = f"ga_{slugify(mission.name) or 'mission'}_{mission.id}_{int(time.time())}"
        filename_no_ext = os.path.join(out_dir, base)

        python_bin = self._pick_python()
        cmd = [
            python_bin, "-m", "scoop", "-n", str(ncores),
            script_rel,
            "--mission_id", str(mission.id),
            "--ngen", str(ngen),
            "--population_size", str(population_size),
            "--filename", filename_no_ext,
            "--max-time", str(max_time),
            "--borderline_time", str(borderline_time),
            "--max_working_speed", str(max_working_speed),
            "--mutation_chance", str(mutation_chance),
        ]

        proc = subprocess.run(cmd, cwd=settings.BASE_DIR, capture_output=True, text=True)
        if proc.returncode != 0:
            return HttpResponse(
                f"Optimization failed:\n\nSTDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}",
                status=500,
            )

        json_path = f"{filename_no_ext}.json"
        xls_path = f"{filename_no_ext}.xls"
        if not os.path.exists(json_path) or not os.path.exists(xls_path):
            return HttpResponse("Optimization finished but outputs are missing.", status=500)

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        serialized = json.dumps(data.get("serialized", []), ensure_ascii=False)
        return serialized, base

    def handle(self, context):
        car_move = self.request.GET.get("carMove", "no")
        direction = self.request.GET.get("direction", "simple")
        start = self.request.GET.get("start", "ne")
        height_diff = self.request.GET.get("heightDiff", False) == "on"
        round_start_zone = self.request.GET.get("roundStartZone", False) == "on"
        feature3 = self.request.GET.get("feature3", False) == "on"
        feature4 = self.request.GET.get("feature4", False) == "on"

        # Format of serialized is: [direction, start, drones, car_move, Optional[list[float] - Requirements for triangulation]
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
            requirements = None
            if len(serialized) > 4:
                from pode import Requirement
                requirements = [Requirement(r) for r in serialized[4]]
                simple_holes_traversal = False
            else:
                simple_holes_traversal = True
            grid, waypoints, car_waypoints, initial_position = get_route(
                car_move=serialized[3],
                direction=serialized[0],
                start=serialized[1],
                field=field,
                holes=holes,
                grid_step=context['mission'].grid_step,
                road=road,
                drones=drones,
                triangulation_requirements=requirements,
                simple_holes_traversal=simple_holes_traversal,
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
                simple_holes_traversal=True,
                # num_subpolygons_rel_to_holes=2,
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
        if "optimize" in request.GET:
            context = self.get_context_data(**kwargs)
            mission = context["mission"]
            res = self._optimize_now(mission)
            if isinstance(res, HttpResponse):
                return res
            serialized, base = res
            q = {
                "serialized": serialized,
                "excel": base,
                "carMove": request.GET.get("carMove", "no"),
                "direction": request.GET.get("direction", "simple"),
                "start": request.GET.get("start", "ne"),
            }
            qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in q.items())
            return HttpResponseRedirect(f"{request.path}?{qs}")

        if "downloadExcel" in self.request.GET:
            base = self.request.GET.get("excel", "")
            if not base or any(c in base for c in ("/", "\\", "..")):
                return HttpResponse(status=400)
            path = os.path.join(settings.MEDIA_ROOT, "opt_results", base + ".xls")
            if not os.path.exists(path):
                return HttpResponse(status=404)
            return FileResponse(open(path, "rb"), as_attachment=True, filename=f"{base}.xls")
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
                            "height": float(height_absolute) + float(request.GET.get("height", 450.0)),
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


def _extract_polygons_from_kml(uploaded_file):
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    tree = ET.parse(uploaded_file)
    root = tree.getroot()
    items = []
    for pm in root.findall(".//kml:Placemark", ns):
        name = (pm.findtext("kml:name", default="", namespaces=ns) or "").strip()
        poly = pm.find(".//kml:Polygon", ns)
        if poly is None:
            continue
        coords_el = poly.find(".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", ns)
        if coords_el is None or not (coords_el.text or "").strip():
            continue
        pts = []
        for token in (coords_el.text or "").strip().split():
            parts = token.split(",")
            if len(parts) >= 2:
                lon = float(parts[0])
                lat = float(parts[1])
                pts.append([lat, lon])
        if len(pts) >= 3 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) >= 3:
            items.append({"name": name or f"Поле {len(items) + 1}", "points": pts})
    return items


@require_http_methods(["GET", "POST"])
def import_kml_fields(request):
    if request.method == "POST" and request.FILES.get("kml"):
        polygons = _extract_polygons_from_kml(request.FILES["kml"])
        return render(
            request,
            "mainapp/field_kml_import.html",
            {"polygons_json": json.dumps(polygons, ensure_ascii=False)},
        )
    return render(request, "mainapp/field_kml_import.html")
