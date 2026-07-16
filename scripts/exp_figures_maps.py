"""Publication map figures: campaign layouts + example solved plans.

Produces (into experiments/figures/):
  fig8_campaigns.png     gallery of all campaign geometries (fields, roads, holes)
  fig9_example_plan.png  (a) best solved plan for one campaign: per-airframe drone
                         paths, truck stops, inter-field transit with visit order;
                         (b) zoom into an obstacle field: zamboni sweep + detours

The solved plan is reconstructed from the best canonical-GA record in
scripts/exp_results.jsonl by re-running the deterministic route constructor
with the recorded best individual's parameters.

Run: venv39\\Scripts\\python.exe scripts/exp_figures_maps.py
"""

import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarmown.settings")
import django

django.setup()

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402

from scripts.exp_analyze import DISPLAY  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIG_DIR = ROOT / "experiments" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

MANIFEST = json.loads((HERE / "exp_manifest.json").read_text(encoding="utf-8"))
RESULTS = HERE / "exp_results.jsonl"

ROLE_ORDER = [
    "C2close",
    "C2far",
    "C3line",
    "C3tri",
    "C3big",
    "C5mixed",
    "C5holes",
    "C5varied",
    "C5size",
    "C10grid",
    "C15scatter",
]

DRONE_COLORS = {
    223: ("#17becf", "Scout (Mini-class)"),
    224: ("#1f77b4", "Light (Phantom-class)"),
    225: ("#ff7f0e", "Mid (Mavic-class)"),
    226: ("#2ca02c", "Long (Evo-class)"),
    227: ("#d62728", "Heavy (M300-class)"),
}


def km_xy(lon, lat, lon0, lat0):
    """Equirectangular local km coordinates around (lon0, lat0)."""
    return (lon - lon0) * 111.2 * math.cos(math.radians(lat0)), (lat - lat0) * 111.2


def campaign_geo(cd):
    """Extract [lon,lat] geometry lists + local-km converter for a campaign."""
    lats = [pt[1] for fd in cd["fields_data"] for pt in fd["field"]]
    lons = [pt[0] for fd in cd["fields_data"] for pt in fd["field"]]
    lon0, lat0 = min(lons), min(lats)

    def conv(pts):  # pts: [[lon, lat], ...]
        return [km_xy(p[0], p[1], lon0, lat0) for p in pts]

    return conv, lon0, lat0


def draw_campaign(ax, cd, conv, field_face="#e8f0e0"):
    for fd in cd["fields_data"]:
        xy = conv(fd["field"])
        ax.add_patch(MplPolygon(xy, closed=True, facecolor=field_face, edgecolor="black", lw=0.8, zorder=1))
        for hole in fd["holes"]:
            hxy = conv(hole)
            ax.add_patch(
                MplPolygon(hxy, closed=True, facecolor="white", edgecolor="dimgray", hatch="///", lw=0.6, zorder=2)
            )
        rxy = conv(fd["road"])
        ax.plot([p[0] for p in rxy], [p[1] for p in rxy], color="dimgray", lw=2.0, solid_capstyle="butt", zorder=3)
    ax.set_aspect("equal")
    ax.autoscale_view()


def fig_campaign_gallery():
    from scripts.ga_multi_common import load_campaign

    fig = plt.figure(figsize=(16, 13))
    gs = fig.add_gridspec(4, 4, height_ratios=[1.1, 1.1, 1.1, 0.5])
    # compact campaigns on three rows; the two wide thin strips span two columns each
    slots = [
        ("C2close", gs[0, 0]),
        ("C3tri", gs[0, 1]),
        ("C3big", gs[0, 2]),
        ("C5mixed", gs[0, 3]),
        ("C5holes", gs[1, 0]),
        ("C5varied", gs[1, 1]),
        ("C5size", gs[1, 2]),
        ("C10grid", gs[1, 3]),
        ("C15scatter", gs[2, 1:3]),
        ("C2far", gs[3, 0:2]),
        ("C3line", gs[3, 2:4]),
    ]
    for role, slot in slots:
        ax = fig.add_subplot(slot)
        cd = load_campaign(MANIFEST[role])
        conv, _, _ = campaign_geo(cd)
        draw_campaign(ax, cd, conv)
        ax.set_title(f"{DISPLAY.get(role, role)} (N={cd['num_fields']})", fontsize=10)
        ax.tick_params(labelsize=7)
        ax.set_xlabel("km", fontsize=8)
        ax.margins(0.08)
    fig.suptitle("Test campaigns: field boundaries, service roads (thick gray), obstacles (hatched)", y=0.995)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig8_campaigns.png", dpi=200)
    plt.close(fig)
    print(f"-> {FIG_DIR / 'fig8_campaigns.png'}")


def best_canonical_rec(role):
    best = None
    if not RESULTS.exists():
        return None
    with open(RESULTS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if "error" in r or r.get("best_ind") is None:
                continue
            if (
                r["role"] == role
                and r["method"] == "ga"
                and r["ablation"] == "full"
                and r["crossover"] == "ox"
                and r.get("truck_speed") is None
                and (best is None or r["best_fit"] < best["best_fit"])
            ):
                best = r
    return best


def reconstruct_routes(cd, ind, order):
    """Re-run the deterministic route constructor for the recorded best plan.

    Returns per visited field: dict(field_idx, waypoints, car_waypoints).
    """
    from mainapp.service_routing import get_route
    from scripts.ga_common import make_pyproj_transformer

    tr = make_pyproj_transformer()
    all_drones = cd["drones_list"]
    out = []
    for field_idx in order:
        fd = cd["fields_data"][field_idx]
        drones = [all_drones[i] for i in ind["drones"][field_idx]]
        avoidance_config = {
            "strategy": "2d",
            "height_min": 10,
            "height_max": 120,
            "safety_margin": 5,
            "climb_rate": 3,
            "descent_rate": 2,
            "energy_per_meter_climb": 1.5,
            "hole_heights": [0.0] * len(fd["holes"]),
            "strategy_params": None,
        }
        kwargs = dict(
            car_move=ind["car_points"][field_idx],
            direction=ind["directions"][field_idx],
            start=ind["starts"][field_idx],
            field=[pt[:] for pt in fd["field"]],
            grid_step=cd["campaign"].grid_step,
            road=[pt[:] for pt in fd["road"]],
            drones=drones,
            pyproj_transformer=tr,
            avoidance_config=avoidance_config,
        )
        if fd["holes"]:
            kwargs["holes"] = [[pt[:] for pt in hole] for hole in fd["holes"]]
            kwargs["simple_holes_traversal"] = True
        _grid, waypoints, car_wps, _ = get_route(**kwargs)
        out.append({"field_idx": field_idx, "waypoints": waypoints, "car_waypoints": car_wps})
    return out


def draw_plan(ax, cd, conv, routes, order, show_transit=True, lw=0.7):
    draw_campaign(ax, cd, conv)
    used_ids = set()
    for fr in routes:
        for flight in fr["waypoints"]:
            if not flight:
                continue
            did = flight[0]["drone"]["id"]
            used_ids.add(did)
            color = DRONE_COLORS.get(did, ("#7f7f7f", str(did)))[0]
            # split into spray (solid) and ferry/detour (dotted) segments
            pts = [km_xy(w["lon"], w["lat"], conv_lon0[0], conv_lon0[1]) for w in flight]
            for i in range(len(pts) - 1):
                spray = flight[i + 1]["spray_on"] and flight[i]["spray_on"]
                ax.plot(
                    [pts[i][0], pts[i + 1][0]],
                    [pts[i][1], pts[i + 1][1]],
                    color=color,
                    lw=lw if spray else lw * 0.7,
                    ls="-" if spray else ":",
                    alpha=0.95 if spray else 0.6,
                    zorder=4,
                )
        # truck stops
        for cw in fr["car_waypoints"]:
            x, y = km_xy(cw[0], cw[1], conv_lon0[0], conv_lon0[1])
            ax.plot(x, y, marker="s", color="black", ms=4, zorder=6)
    if show_transit:
        for k in range(len(order)):
            fd = cd["fields_data"][order[k]]
            cx, cy = km_xy(
                sum(p[0] for p in fd["field"]) / len(fd["field"]),
                sum(p[1] for p in fd["field"]) / len(fd["field"]),
                conv_lon0[0],
                conv_lon0[1],
            )
            ax.annotate(
                str(k + 1),
                (cx, cy),
                fontsize=11,
                fontweight="bold",
                ha="center",
                va="center",
                color="black",
                zorder=7,
                bbox=dict(boxstyle="circle,pad=0.15", fc="white", ec="black", lw=0.8, alpha=0.9),
            )
            if k + 1 < len(order):
                a = cd["fields_data"][order[k]]["road"][-1]
                b = cd["fields_data"][order[k + 1]]["road"][0]
                xa, ya = km_xy(a[0], a[1], conv_lon0[0], conv_lon0[1])
                xb, yb = km_xy(b[0], b[1], conv_lon0[0], conv_lon0[1])
                ax.annotate(
                    "",
                    xy=(xb, yb),
                    xytext=(xa, ya),
                    arrowprops=dict(arrowstyle="->", color="black", lw=1.0, ls="--", alpha=0.7),
                    zorder=5,
                )
    ax.set_aspect("equal")
    return used_ids


conv_lon0 = (0.0, 0.0)  # module-level (lon0, lat0) used by draw_plan


def fig_example_plan(main_role="C5size", zoom_role="C5holes", big_role="C3big"):
    global conv_lon0
    from scripts.ga_multi_common import load_campaign

    rec_main = best_canonical_rec(main_role)
    rec_zoom = best_canonical_rec(zoom_role)
    rec_big = best_canonical_rec(big_role)
    if rec_main is None or rec_zoom is None:
        print("no canonical records yet -- skipping fig9")
        return

    ncols = 3 if rec_big is not None else 2
    ratios = [1.5, 1, 1] if rec_big is not None else [1.5, 1]
    fig, axes = plt.subplots(1, ncols, figsize=(5.2 * ncols + 4, 6.5), gridspec_kw={"width_ratios": ratios})
    ax1, ax2 = axes[0], axes[1]

    # (a) full campaign plan
    cd = load_campaign(MANIFEST[main_role])
    conv, lon0, lat0 = campaign_geo(cd)
    conv_lon0 = (lon0, lat0)
    routes = reconstruct_routes(cd, rec_main["best_ind"], rec_main["best_order"])
    used = draw_plan(ax1, cd, conv, routes, rec_main["best_order"])
    ax1.set_title(
        f"(a) {DISPLAY.get(main_role, main_role)}: best plan, cost ${rec_main['best_fit']:.0f} "
        f"(visit order circled, truck transit dashed)",
        fontsize=10,
    )
    ax1.set_xlabel("km")
    ax1.set_ylabel("km")

    # (b) zoom: the obstacle field with the most holes
    cdz = load_campaign(MANIFEST[zoom_role])
    convz, lon0z, lat0z = campaign_geo(cdz)
    conv_lon0 = (lon0z, lat0z)
    zoom_field = max(range(len(cdz["fields_data"])), key=lambda i: len(cdz["fields_data"][i]["holes"]))
    routesz = reconstruct_routes(cdz, rec_zoom["best_ind"], rec_zoom["best_order"])
    routesz = [r for r in routesz if r["field_idx"] == zoom_field]
    usedz = draw_plan(ax2, cdz, convz, routesz, [zoom_field], show_transit=False, lw=1.1)
    fd = cdz["fields_data"][zoom_field]
    xs = [km_xy(p[0], p[1], lon0z, lat0z)[0] for p in fd["field"]]
    ys = [km_xy(p[0], p[1], lon0z, lat0z)[1] for p in fd["field"]]
    pad = 0.25
    ax2.set_xlim(min(xs) - pad, max(xs) + pad)
    ax2.set_ylim(min(ys) - pad - 0.2, max(ys) + pad)
    ax2.set_title(
        f"(b) {DISPLAY.get(zoom_role, zoom_role)}: coverage of an obstacle field\n(dotted = ferry/detour legs)",
        fontsize=10,
    )
    ax2.set_xlabel("km")

    # (c) the C3big giant field: several airframes covering one field concurrently
    usedb = set()
    if rec_big is not None:
        ax3 = axes[2]
        cdb = load_campaign(MANIFEST[big_role])
        convb, lon0b, lat0b = campaign_geo(cdb)
        conv_lon0 = (lon0b, lat0b)
        # field 0 is the 2.8 x 2.8 km field
        routesb = reconstruct_routes(cdb, rec_big["best_ind"], rec_big["best_order"])
        routesb = [r for r in routesb if r["field_idx"] == 0]
        usedb = draw_plan(ax3, cdb, convb, routesb, [0], show_transit=False, lw=1.0)
        fdb = cdb["fields_data"][0]
        xs = [km_xy(p[0], p[1], lon0b, lat0b)[0] for p in fdb["field"]]
        ys = [km_xy(p[0], p[1], lon0b, lat0b)[1] for p in fdb["field"]]
        pad = 0.3
        ax3.set_xlim(min(xs) - pad, max(xs) + pad)
        ax3.set_ylim(min(ys) - pad - 0.25, max(ys) + pad)
        ax3.set_title(
            f"(c) {DISPLAY.get(big_role, big_role)}: one ~780 ha field split\n"
            f"across several drones (concurrent flights)",
            fontsize=10,
        )
        ax3.set_xlabel("km")

    handles = [
        Line2D([], [], color=DRONE_COLORS[d][0], lw=2, label=DRONE_COLORS[d][1])
        for d in DRONE_COLORS
        if d in (used | usedz | usedb)
    ]
    handles += [
        Line2D([], [], color="black", marker="s", ls="none", ms=5, label="truck stop"),
        Line2D([], [], color="dimgray", lw=2.5, label="service road"),
    ]
    ax1.legend(handles=handles, fontsize=8, loc="best")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig9_example_plan.png", dpi=200)
    plt.close(fig)
    print(f"-> {FIG_DIR / 'fig9_example_plan.png'}")


if __name__ == "__main__":
    fig_campaign_gallery()
    fig_example_plan()
