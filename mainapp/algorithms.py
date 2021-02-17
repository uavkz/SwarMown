from mainapp.services_draw import  generate_zamboni

WAYPOINTS_ALGORITHMS = {
    "zamboni": {
        "callable": generate_zamboni,
    }
}
