import contextlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET

from django.conf import settings
from django.db import transaction
from django.http import FileResponse, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.utils.text import slugify
from django.views import View
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView, TemplateView

from mainapp.models import Drone, Field, Mission, Waypoint
from mainapp.service_routing import get_route
from mainapp.services_export import export_csv, export_mavlink_json
from mainapp.utils import flatten_grid


class Index(View):
    def get(self, request, **kwargs):
        if request.user.is_authenticated:
            return HttpResponseRedirect(reverse_lazy("mainapp:list_mission"))
        else:
            return HttpResponseRedirect(reverse_lazy("mainapp:login"))


class ManageRouteView(TemplateView):
    template_name = "mainapp/manage_route.html"

    def _pick_python(self):
        candidates = []
        env_py = os.environ.get("GA_PYTHON")
        if env_py:
            candidates.append(env_py)
        with contextlib.suppress(Exception):
            candidates.append(sys.executable)
        candidates.append(os.path.join(settings.BASE_DIR, "venv39", "Scripts", "python.exe"))
        candidates.append("python")

        for p in candidates:
            try:
                subprocess.run(
                    [p, "-c", "import scoop"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
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
            python_bin,
            "-m",
            "scoop",
            "-n",
            str(ncores),
            script_rel,
            "--mission_id",
            str(mission.id),
            "--ngen",
            str(ngen),
            "--population_size",
            str(population_size),
            "--filename",
            filename_no_ext,
            "--max-time",
            str(max_time),
            "--borderline_time",
            str(borderline_time),
            "--max_working_speed",
            str(max_working_speed),
            "--mutation_chance",
            str(mutation_chance),
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

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        serialized = json.dumps(data.get("serialized", []), ensure_ascii=False)
        return serialized, base

    def _compute_route(self, context):
        """Load field data and compute route, populating context."""
        request = self.request
        serialized = request.GET.get("serialized", False)
        if serialized:
            try:
                serialized = json.loads(serialized)
            except json.JSONDecodeError:
                serialized = json.loads(serialized.replace("'", '"'))

        field_obj = context["mission"].field
        field = [[y, x] for x, y in json.loads(field_obj.points_serialized)]
        road = [[y, x] for x, y in json.loads(field_obj.road_serialized)]
        holes = [[[y, x] for x, y in hole] for hole in json.loads(field_obj.holes_serialized)]

        context["field_flat"] = [coord for point in field for coord in point]
        context["field_id"] = field_obj.id if field_obj else ""
        context["field"] = field
        context["road"] = road
        context["holes"] = holes
        context["grid_step"] = context["mission"].grid_step
        context["number_of_drones"] = context["mission"].drones.all().count()

        if serialized:
            drones = [list(context["mission"].drones.all().order_by("id"))[i] for i in serialized[2]]
            requirements = None
            simple_holes_traversal = True
            if len(serialized) > 4:
                from pode import Requirement

                requirements = [Requirement(r) for r in serialized[4]]
                simple_holes_traversal = False
            grid, waypoints, car_waypoints, initial_position = get_route(
                car_move=serialized[3],
                direction=serialized[0],
                start=serialized[1],
                field=field,
                holes=holes,
                grid_step=context["mission"].grid_step,
                road=road,
                drones=drones,
                triangulation_requirements=requirements,
                simple_holes_traversal=simple_holes_traversal,
            )
        else:
            grid, waypoints, car_waypoints, initial_position = get_route(
                car_move=request.GET.get("carMove", "no"),
                direction=request.GET.get("direction", "simple"),
                start=request.GET.get("start", "ne"),
                field=field,
                holes=holes,
                grid_step=context["mission"].grid_step,
                road=road,
                drones=context["mission"].drones.all().order_by("id"),
                simple_holes_traversal=True,
            )

        context["grid"] = list(flatten_grid(grid))
        context["initial"] = initial_position
        context["waypoints"] = waypoints
        context["pickup_waypoints"] = car_waypoints

    def _handle_optimize(self, context):
        mission = context["mission"]
        res = self._optimize_now(mission)
        if isinstance(res, HttpResponse):
            return res
        serialized, base = res
        q = {
            "serialized": serialized,
            "excel": base,
            "carMove": self.request.GET.get("carMove", "no"),
            "direction": self.request.GET.get("direction", "simple"),
            "start": self.request.GET.get("start", "ne"),
        }
        qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in q.items())
        return HttpResponseRedirect(f"{self.request.path}?{qs}")

    def _handle_download_excel(self):
        base = self.request.GET.get("excel", "")
        if not base or any(c in base for c in ("/", "\\", "..")):
            return HttpResponse(status=400)
        path = os.path.join(settings.MEDIA_ROOT, "opt_results", base + ".xls")
        if not os.path.exists(path):
            return HttpResponse(status=404)
        return FileResponse(open(path, "rb"), as_attachment=True, filename=f"{base}.xls")

    def _handle_save(self, context):
        with transaction.atomic():
            i = 0
            context["mission"].current_waypoints_status = 1
            context["mission"].save()
            context["mission"].current_waypoints.all().delete()
            waypoints_to_create = []
            for waypoints in context["waypoints"]:
                for wp in waypoints:
                    waypoints_to_create.append(
                        Waypoint(
                            drone_id=wp["drone"]["id"],
                            index=i,
                            lat=wp["lat"],
                            lon=wp["lon"],
                            height=wp["height"],
                            speed=wp["speed"],
                            acceleration=wp["acceleration"],
                            spray_on=wp["spray_on"],
                        )
                    )
                    i += 10
            created = Waypoint.objects.bulk_create(waypoints_to_create)
            context["mission"].current_waypoints.set(created)
            context["mission"].current_waypoints_status = 2
            context["mission"].save()
        return HttpResponseRedirect(reverse_lazy("mainapp:list_mission"))

    def _handle_export_csv(self, context):
        height_offset = float(self.request.GET.get("height", 450.0))
        height_absolute = self.request.GET.get("height_absolute")
        return export_csv(context["waypoints"], height_offset, height_absolute)

    def _handle_export_json(self, context):
        height_offset = float(self.request.GET.get("height", 450.0))
        height_absolute = self.request.GET.get("height_absolute")
        return export_mavlink_json(context["waypoints"], height_offset, height_absolute)

    def get(self, request, *args, **kwargs):
        if "downloadExcel" in request.GET:
            return self._handle_download_excel()

        # Actions that need route context but return non-template responses
        for param, handler in [
            ("optimize", self._handle_optimize),
            ("submitSave", self._handle_save),
            ("getCsv", self._handle_export_csv),
            ("getJson", self._handle_export_json),
        ]:
            if param in request.GET:
                context = self.get_context_data(**kwargs)
                return handler(context)

        # Normal template rendering — super().get() calls get_context_data() itself
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_staff:
            mission = get_object_or_404(Mission, id=kwargs["mission_id"])
        else:
            mission = get_object_or_404(Mission, id=kwargs["mission_id"], owner=self.request.user)
        context["mission"] = mission
        self._compute_route(context)
        return context


class MissionsCreateView(TemplateView):
    template_name = "mainapp/add_mission.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["types"] = Mission.TYPES
        context["fields"] = (
            Field.objects.all() if self.request.user.is_staff else Field.objects.filter(owner=self.request.user)
        )
        context["drones"] = Drone.objects.all()
        return context

    def post(self, request, **kwargs):
        field = get_object_or_404(Field, id=request.POST["field"])
        if not request.user.is_staff and field.owner_id != request.user.id:
            return HttpResponse(status=403)
        m = Mission.objects.create(
            owner=request.user,
            name=request.POST["name"],
            description=request.POST["description"],
            type=request.POST["type"],
            field=field,
            grid_step=request.POST["grid_step"],
        )
        m.drones.add(*request.POST.getlist("drones"))
        return HttpResponseRedirect(reverse_lazy("mainapp:list_mission"))


class MissionsListView(ListView):
    template_name = "mainapp/list_mission.html"

    def get_queryset(self):
        qs = (
            Mission.objects.all()
            .order_by("-id")
            .select_related("field", "owner")
            .prefetch_related("drones", "current_waypoints")
        )
        return qs if self.request.user.is_staff else qs.filter(owner=self.request.user)


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
                try:
                    lon = float(parts[0])
                    lat = float(parts[1])
                except ValueError:
                    continue
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
