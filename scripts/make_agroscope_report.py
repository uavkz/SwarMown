"""Генерация краткого отчёта (DOCX) по интеграции с AgroScope: импорт KML и выгрузка JSON."""  # noqa: RUF002

from docx import Document
from docx.shared import Pt, RGBColor

CODE_BG = RGBColor(0x2B, 0x2B, 0x2B)
GREY = RGBColor(0x55, 0x55, 0x55)


def add_code(doc, text):
    """Вставить блок кода моноширинным шрифтом."""
    for line in text.split("\n"):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.left_indent = Pt(10)
        run = p.add_run(line if line else " ")
        run.font.name = "Consolas"
        run.font.size = Pt(8.5)


def add_caption(doc, text):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.italic = True
    r.font.size = Pt(9)
    r.font.color.rgb = GREY


doc = Document()

# базовый шрифт
doc.styles["Normal"].font.name = "Calibri"
doc.styles["Normal"].font.size = Pt(11)

title = doc.add_heading("Интеграция с AgroScope: листинги кода", level=0)

intro = doc.add_paragraph()
intro.add_run(
    "Отчёт по задаче календарного плана. Реализованы два направления обмена данными с системой AgroScope:"
).bold = False
doc.add_paragraph("п.2 — импорт задания из KML-файла (зоны поля + метаданные задачи);", style="List Bullet")
doc.add_paragraph(
    "п.3 — выгрузка результата в виде единого MAVLink-плана (JSON) с блоком agroScopeMeta, "
    "по которому AgroScope привязывает маршрут к задаче и разбивает его обратно по зонам.",
    style="List Bullet",
)

doc.add_paragraph(
    "Весь код интеграции вынесен в отдельный модуль mainapp/services_agroscope.py "
    "и подключён к web-приложению (импорт — кнопка загрузки KML, выгрузка — кнопка экспорта JSON)."
)

# ------------------------------------------------------------------ п.2
doc.add_heading("1. Загрузка KML (импорт задания AgroScope)", level=1)
doc.add_paragraph(
    "KML разбирается стандартным xml.etree без сторонних библиотек. Из документа берутся "
    "метаданные задачи (ExtendedData), из каждого Placemark — полигон зоны. Парсер устойчив "
    "к namespace KML и совместим со старыми файлами без метаданных."
)

add_caption(doc, "Листинг 1.1 — разбор KML в структуру {meta, zones}  (services_agroscope.py)")
add_code(
    doc,
    '''def parse_agroscope_kml(source):
    """Парсит KML задания AgroScope в {"meta": {...}, "zones": [...]}."""
    root = ET.parse(source).getroot()
    document = next((el for el in root.iter() if el.tag.endswith("Document")), root)

    # метаданные задачи на уровне документа (Приложение 1)
    doc_data = _extended_data(document)
    meta = {"name": ...}
    for field in _DOC_META_FIELDS:          # source, task_id, field_name, crop, ...
        meta[field] = doc_data.get(field) or None

    zones = []
    for pm in _findall_any_ns(root, "Placemark"):
        polygon = next((el for el in pm.iter() if el.tag.endswith("Polygon")), None)
        if polygon is None:
            continue
        outer = next((el for el in polygon.iter()
                      if el.tag.endswith("outerBoundaryIs")), polygon)
        coords_el = next((el for el in outer.iter()
                          if el.tag.endswith("coordinates")), None)
        if coords_el is None:
            continue
        points = _parse_coordinates(coords_el.text)   # "lon,lat" -> [[lon, lat], ...]
        if len(points) < 3:
            continue

        pm_data = _extended_data(pm)
        zone_id = pm_data.get("zone_id") or name or str(len(zones) + 1)
        zones.append({
            "zone_id": zone_id,
            "name": name or f"Зона {len(zones) + 1}",
            "task_id": pm_data.get("task_id") or meta.get("task_id"),
            "points": points,
        })
    return {"meta": meta, "zones": zones}''',
)

add_caption(doc, "Листинг 1.2 — разбор координат KML в пары [lon, lat]")
add_code(
    doc,
    '''def _parse_coordinates(text):
    """KML <coordinates> = "lon,lat[,alt]" -> [[lon, lat], ...]."""
    points = []
    for token in (text or "").strip().split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                lon, lat = float(parts[0]), float(parts[1])
            except ValueError:
                continue
            points.append([lon, lat])
    # KML-кольцо повторяет первую точку в конце — убираем дубль
    if len(points) >= 4 and points[0] == points[-1]:
        points = points[:-1]
    return points''',
)

add_caption(doc, "Листинг 1.3 — подключение импорта к web-приложению  (views.py)")
add_code(
    doc,
    '''@require_http_methods(["GET", "POST"])
def import_kml_fields(request):
    if request.method == "POST" and request.FILES.get("kml"):
        polygons = _extract_polygons_from_kml(request.FILES["kml"])
        return render(request, "mainapp/field_kml_import.html",
                      {"polygons_json": json.dumps(polygons, ensure_ascii=False)})
    return render(request, "mainapp/field_kml_import.html")


def _extract_polygons_from_kml(uploaded_file):
    """Зоны из KML для UI; метаданные задачи сохраняются в поле (Field)."""
    parsed = parse_agroscope_kml(uploaded_file)
    meta = parsed["meta"]
    items = []
    for zone in parsed["zones"]:
        pts = [[lat, lon] for lon, lat in zone["points"]]   # -> [lat, lon] для Leaflet
        zone_meta = {
            "task_id": zone["task_id"], "task_number": meta.get("task_number"),
            "field_id": meta.get("field_id"), "field_name": meta.get("field_name"),
            "crop": meta.get("crop"), "planned_date": meta.get("planned_date"),
            "zone_id": zone["zone_id"], "zone_name": zone["name"],
        }
        items.append({"name": ..., "points": pts, "agroscope_meta": zone_meta})
    return items''',
)

# ------------------------------------------------------------------ п.3
doc.add_heading("2. Выгрузка JSON (ответ для AgroScope)", level=1)
doc.add_paragraph(
    "После планирования маршрута формируется один MAVLink-план (формат QGroundControl) "
    "со служебным блоком agroScopeMeta. В блоке хранятся реквизиты задачи и для каждой зоны — "
    "индексы её точек в общем списке маршрута (waypointIndices), чтобы AgroScope разбил "
    "маршрут обратно по зонам."
)

add_caption(doc, "Листинг 2.1 — сборка плана с блоком agroScopeMeta  (services_agroscope.py)")
add_code(
    doc,
    '''def build_agroscope_plan(zones, meta, route_generated_at, altitude_world=855):
    """Единый MAVLink-план QGroundControl с блоком agroScopeMeta."""
    # сводим точки всех зон в один список, запоминая размер каждой зоны
    flat, zone_counts = [], []
    for zone in zones:
        wps = zone["waypoints"]
        if not wps:
            continue
        zone_counts.append((zone, len(wps)))
        flat.extend(wps)

    altitude = flat[0]["height"] if flat else 80
    # item 0 = home (530), item 1 = takeoff (22), остальные = waypoint (16)
    plan_items = [_mission_item(i, wp["lat"], wp["lon"], wp.get("height", altitude))
                  for i, wp in enumerate(flat)]

    agro_zones, cursor = [], 0
    for zone, count in zone_counts:
        # пропускаем служебные item 0 (home) и 1 (takeoff) — они вне зон
        zone_indices = [i for i in range(cursor, cursor + count) if i >= 2]
        cursor += count
        agro_zones.append({
            "zoneId": _to_int(zone["zone_id"]),
            "zoneName": zone.get("zone_name") or zone.get("name"),
            "waypointIndices": zone_indices,
        })

    return {
        "fileType": "Plan", "groundStation": "QGroundControl", "version": 1,
        "mission": {"items": plan_items, "version": 2, ...},
        "agroScopeMeta": {
            "taskId": meta.get("task_id"),
            "taskNumber": _to_int(meta.get("task_number")),
            "fieldId": meta.get("field_id"), "fieldName": meta.get("field_name"),
            "crop": meta.get("crop"), "plannedDate": meta.get("planned_date"),
            "routeGeneratedAt": route_generated_at,
            "zones": agro_zones,
        },
    }''',
)

add_caption(doc, "Листинг 2.2 — HTTP-выгрузка JSON одним файлом  (services_export.py)")
add_code(
    doc,
    '''def export_agroscope_json(zones, meta, route_generated_at,
                          height_offset=None, height_absolute_override=None):
    """Ответ AgroScope (п.3): один MAVLink-план с блоком agroScopeMeta."""
    # проставляем высоты точек (рельеф + смещение либо фикс. значение)
    if height_absolute_override is not None:
        for zone in zones:
            for wp in zone["waypoints"]:
                wp["height"] = float(height_absolute_override)
    elif height_offset is not None:
        elevations = _resolve_elevations([z["waypoints"] for z in zones])
        for zone in zones:
            for wp in zone["waypoints"]:
                wp["height"] = elevations[(round(wp["lat"], 3),
                                           round(wp["lon"], 3))] + height_offset

    plan = build_agroscope_plan(zones, meta, route_generated_at)
    task_num = meta.get("task_number") or "x"
    response = HttpResponse(json.dumps(plan, ensure_ascii=False),
                            content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="task_{task_num}_route.json"'
    return response''',
)

add_caption(doc, "Листинг 2.3 — вызов выгрузки по кнопке экспорта JSON  (views.py)")
add_code(
    doc,
    """def _handle_export_json(self, context):
    meta_raw = context["mission"].field.agroscope_meta_serialized
    if meta_raw:
        # поле из AgroScope (п.3): отдаём план с блоком agroScopeMeta
        meta = json.loads(meta_raw)
        flat = [{"lat": wp["lat"], "lon": wp["lon"], "height": wp["height"]}
                for flight in context["waypoints"] for wp in flight]
        zone = {"zone_id": meta.get("zone_id"),
                "zone_name": meta.get("zone_name") or context["mission"].field.name,
                "waypoints": flat}
        return export_agroscope_json([zone], meta,
                                     timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     height_offset, height_absolute)
    return export_mavlink_json(context["waypoints"], height_offset, height_absolute)""",
)

# ------------------------------------------------------------------ итог
doc.add_heading("Итог", level=1)
doc.add_paragraph(
    "Цикл обмена с AgroScope замкнут: задание (KML) загружается в планировщик, маршрут "
    "оптимизируется, результат выгружается единым JSON с метаданными зон. Реализация покрыта "
    "автотестами (test_services_agroscope.py, test_views.py)."
)
p = doc.add_paragraph()
r = p.add_run(
    "Файлы: mainapp/services_agroscope.py, mainapp/services_export.py, "
    "mainapp/views.py, mainapp/models.py (поле agroscope_meta_serialized)."
)
r.font.size = Pt(9)
r.font.color.rgb = GREY

out = "AgroScope_интеграция_листинги.docx"
doc.save(out)
print("saved:", out)
