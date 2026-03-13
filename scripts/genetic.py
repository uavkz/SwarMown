"""GA optimizer for missions without holes (simple traversal)."""

from scripts.ga_common import (
    bootstrap_django,
    build_argparser,
    custom_mutate,
    evaluate_individual,
    load_mission,
    make_pyproj_transformer,
    run_ga,
    save_results,
    setup_toolbox,
)

bootstrap_django()

args = build_argparser().parse_args()
mission_data = load_mission(args.mission_id)
pyproj_transformer = make_pyproj_transformer()


def evaluate(individual):
    return evaluate_individual(
        individual,
        mission_data,
        args,
        pyproj_transformer,
        simple_holes_traversal=True,
    )


def mutate(ind):
    return custom_mutate(ind, mission_data["num_drones"], args.mutation_chance)


toolbox = setup_toolbox(mission_data["num_drones"], evaluate, mutate)


def run():
    iterations = run_ga(toolbox, args.population_size, args.ngen)
    save_results(iterations, args, mission_data["mission"])


if __name__ == "__main__":
    run()
