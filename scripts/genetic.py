"""GA optimizer for missions without holes (simple traversal)."""

from scripts.ga_common import (
    bootstrap_django,
    build_argparser,
    build_avoidance_config,
    custom_mutate,
    evaluate_individual,
    load_mission,
    make_pyproj_transformer,
    parse_obstacle_heights,
    run_ga,
    save_results,
    setup_toolbox,
)

bootstrap_django()

args = build_argparser().parse_args()
mission_data = load_mission(args.mission_id)
pyproj_transformer = make_pyproj_transformer()

# 3D avoidance setup
num_holes = len(mission_data["holes"])
hole_heights = parse_obstacle_heights(args, num_holes)
avoidance_config = build_avoidance_config(args, hole_heights)


def evaluate(individual):
    return evaluate_individual(
        individual,
        mission_data,
        args,
        pyproj_transformer,
        simple_holes_traversal=True,
        avoidance_config=avoidance_config,
    )


def mutate(ind):
    return custom_mutate(ind, mission_data["num_drones"], args.mutation_chance, args.avoidance_strategy)


toolbox = setup_toolbox(
    mission_data["num_drones"],
    evaluate,
    mutate,
    avoidance_strategy=args.avoidance_strategy,
    num_holes=num_holes,
)


def run():
    iterations = run_ga(toolbox, args.population_size, args.ngen)
    save_results(iterations, args, mission_data["mission"])


if __name__ == "__main__":
    run()
