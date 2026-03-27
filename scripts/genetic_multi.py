"""GA optimizer for multi-field campaigns (2D mode)."""

from scripts.ga_multi_common import (
    bootstrap_django,
    build_multi_argparser,
    evaluate_multi_individual,
    load_campaign,
    make_pyproj_transformer,
    mutate_multi,
    run_multi_ga,
    save_multi_results,
    setup_multi_toolbox,
)

bootstrap_django()

args = build_multi_argparser().parse_args()
campaign_data = load_campaign(args.campaign_id)
pyproj_transformer = make_pyproj_transformer()


def evaluate(individual):
    return evaluate_multi_individual(
        individual,
        campaign_data,
        args,
        pyproj_transformer,
    )


def mutate(ind):
    return mutate_multi(
        ind,
        campaign_data["num_drones"],
        campaign_data["num_fields"],
        args.mutation_chance,
        order_mutation=args.order_mutation,
        ablation=args.ablation,
    )


toolbox = setup_multi_toolbox(
    campaign_data["num_fields"],
    campaign_data["num_drones"],
    evaluate,
    mutate,
    crossover_type=args.order_crossover,
    ablation=args.ablation,
)


def run():
    iterations = run_multi_ga(toolbox, args.population_size, args.ngen)
    save_multi_results(iterations, args, campaign_data)


if __name__ == "__main__":
    run()
