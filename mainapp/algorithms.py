from mainapp.ga_services import generate_waypoints_ga
from mainapp.services_draw import get_waypoints, generate_zamboni

WAYPOINTS_ALGORITHMS = {
    "simple": {
        "callable": get_waypoints,
    },
    "ga": {
        "callable": generate_waypoints_ga,
    },
    "zamboni": {
        "callable": generate_zamboni,
    }
}
