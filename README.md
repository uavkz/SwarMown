# SwarMown: multi-field coverage planning for a truck-carried UAV fleet

This repository holds the planner, the campaign generators, the experiment harness, the raw results and the analysis scripts of the paper

> K. Yakunin, V. Levashenko, E. Zaitseva, S. Cherny, and R. I. Mukhamediev, "Multi-Field Coverage Path Planning for a Truck-Carried Heterogeneous UAV Fleet: Joint Genetic Optimization Versus a Two-Stage Planner," manuscript submitted to *IEEE Access*, 2026.

Every table and figure of the paper is regenerated from the files in this repository; see [Reproducing the paper](#reproducing-the-paper). The code also contains the Django web application and the single-field optimizers of the two earlier papers on the same system ([1], [2] below).

## The problem

A light truck carries a fleet of agricultural drones between several fields in one working day. At each field the truck stops on a service road, the drones sweep the parcel in a boustrophedon (lawn-mower) pattern from the stops and return. Under one monetary objective (drone wear, crew time, overtime penalty) the planner chooses

- the order in which the fields are visited,
- the flight direction and the start corner of the sweep at each field,
- which drones of a heterogeneous fleet fly at each field and in what sequence,
- where the truck stops along the road of each field.

Two planners are compared at the same evaluation budget: a joint genetic algorithm (GA) whose chromosome holds all decisions, and a two-stage planner that fixes the visit order first (nearest-neighbour or exact Held–Karp tour) and spends the whole budget on the coverage parameters.

## Main results

Eleven synthetic campaigns of 2 to 15 realistically shaped parcels, 784 optimization runs, 8 seeds per configuration, 2000 evaluations per run.

- The joint GA beats a random search at the same budget on every campaign (3.5–27.6% lower cost, p < 0.001).
- Every decision except the start corner is worth optimizing. Freezing the drone sequence costs up to 86% where a large field needs concurrent flights; the start corner is made redundant by the flight direction.
- The joint GA under-optimizes the visit order at scale. The two-stage planner is never significantly worse and is cheaper from ten fields upward (4.2% and 8.6%); an exact stage-one tour saves a further 4.0% where the working-day limit binds.
- A light drone flies most missions. Additional models appear only where battery range or concurrent flights reduce cost; the heavy class is never selected.

## Repository layout

| Path | Content |
|---|---|
| `mainapp/service_routing.py`, `mainapp/services_draw.py`, `mainapp/utils.py` | Single-field route constructor: coverage grid, boustrophedon sweep, truck stops, drone assignment, obstacle detours, flight-time and cost model |
| `scripts/ga_multi_common.py` | Multi-field campaign model: chromosome, directed transit matrix, one-crew cost model, GA operators, random-keys encoding, ablation modes |
| `scripts/exp_campaigns.py`, `scripts/exp_campaign_varied.py`, `scripts/exp_campaign_big.py` | Deterministic generators of the test campaigns and of the five-class fleet |
| `scripts/exp_run.py` | Experiment harness: builds the job matrix (joint GA, random search, two-stage planner, ablations, operator grid, truck-speed sweep, control studies) and runs it in parallel |
| `scripts/exp_ordering.py`, `scripts/exp_tsp_operators.py` | Ordering subproblem: exact Held–Karp bounds, nearest-neighbour and default tours, operator and encoding study on the pure tour problem |
| `scripts/exp_analyze.py`, `scripts/exp_figures_maps.py` | Tables (`experiments/results_tables.md`, `experiments/results_summary.json`) and figures (`experiments/figures/`) |
| `scripts/exp_results.jsonl`, `scripts/exp_roadside.jsonl`, `scripts/exp_ga_exact.jsonl` | Raw results of all 784 runs: 640-run main matrix, 120-run road-side control study, 24 exact-tour runs |
| `scripts/exp_ordering.json`, `scripts/exp_tsp.json`, `scripts/exp_manifest.json` | Reference tours per campaign, operator study on the tour subproblem, campaign ids in the database |
| `experiments/multi_field_experiments.md` | Experimental protocol: campaigns, fleet, job matrix, run counts, commands |
| `experiments/archive/` | Result files of earlier model versions, not used in the paper |
| `mainapp/`, `restapp/`, `templates/` | Django web application: field editor, route visualization, campaign views, CSV/MAVLink export |
| `scripts/genetic.py`, `scripts/genetic_holes.py` | Single-field optimizers of the earlier papers [1], [2] |

## Setup

Python 3.9 is required (the pinned Django 3.0 does not run on newer interpreters).

```bash
python -m venv venv39
venv39\Scripts\activate            # Windows;  Linux/macOS: source venv39/bin/activate
pip install -r requirements.txt
git clone https://github.com/LostFan123/pode.git && cd pode && git checkout 0ad2db3 && pip install . && cd ..
python manage.py migrate
```

PODE is the polygon-decomposition library used for fields with obstacles. The test suite runs with `python manage.py test`; the multi-field model alone with `python manage.py test mainapp.tests.test_multi_field`.

## Reproducing the paper

All commands run from the repository root inside the virtual environment. The shipped result files are the ones analysed in the paper, so steps 1, 4 and 5 are enough to rebuild every table and figure; steps 2 and 3 re-run the optimization itself.

1. **Create the campaigns and the fleet** in the local database. The first script resets all experiment campaigns and writes `scripts/exp_manifest.json`; the other two add one campaign each and must run after it.

   ```bash
   python scripts/exp_campaigns.py
   python scripts/exp_campaign_varied.py
   python scripts/exp_campaign_big.py
   ```

2. **Ordering subproblem** (minutes): exact, nearest-neighbour, default and worst tours per campaign, then the operator and encoding study on the pure tour problem (30 repetitions per operator pair).

   ```bash
   python scripts/exp_ordering.py          # -> scripts/exp_ordering.json
   python scripts/exp_tsp_operators.py     # -> scripts/exp_tsp.json
   ```

3. **Optimization runs.** One run of 2000 evaluations takes 1.5 min (two fields) to 14 min (C3-big) in one worker process. The main matrix consumed 75 CPU-hours (about 5.5 h with 14 workers), the control study 10 and the exact-tour comparison 3.

   ```bash
   # main matrix, 640 runs
   python scripts/exp_run.py --ngen 40 --pop 50 --seeds 8 --workers 14 --nn_seed --transit_roles C5mixed,C10grid
   # road-side control study, 120 runs
   python scripts/exp_run.py --ngen 40 --pop 50 --seeds 8 --workers 14 --roadside_only --out scripts/exp_roadside.jsonl
   # two-stage planner with the exact stage-one tour, 24 runs
   python scripts/exp_run.py --ngen 40 --pop 50 --seeds 8 --workers 14 --exact_only --out scripts/exp_ga_exact.jsonl
   ```

   Results are appended one JSON record per line as jobs finish, so an interrupted matrix can be continued with `--resume`. `--smoke` runs a two-minute sanity check of the whole pipeline.

4. **Tables and statistics** (a few minutes): `experiments/results_tables.md`, `experiments/results_summary.json` and the statistical figures.

   ```bash
   python scripts/exp_analyze.py
   ```

5. **Map figures**: the campaign gallery and the solved example plans, reconstructed by re-running the route constructor on the recorded best individuals (needs the campaigns of step 1 in the database).

   ```bash
   python scripts/exp_figures_maps.py
   ```

### Where each table and figure of the paper comes from

| Paper | Repository |
|---|---|
| Table 4 (campaigns), Table 5 (fleet) | `scripts/exp_campaigns.py` (`build_layouts`, `FLEET_SPECS`), `exp_campaign_varied.py`, `exp_campaign_big.py` |
| Table 6, GA vs random search | `results_tables.md` Table 1 |
| Table 7, ablations | `results_tables.md` Table 2 |
| Table 8, start-corner control study | `results_tables.md` Table 2c (from `exp_roadside.jsonl`) |
| Table 9, granularity | `results_tables.md` Table 2b |
| Table 10, fleet composition | `results_tables.md` Table 8 |
| Table 11, reference tours | `results_tables.md` Table 6 (`exp_ordering.json`) |
| Table 12, ordering operators and encodings | `results_tables.md` Tables 5 and 5b (`exp_tsp.json`, joint runs) |
| Table 13, scaling and runtime | `results_tables.md` Table 3 |
| Table 14, two-stage planner vs joint GA | `results_tables.md` Table 7 |
| Table 15, exact vs nearest-neighbour stage-one tour | `results_tables.md` Table 7b (`exp_ga_exact.jsonl`) |
| Table 16 (Appendix A), truck-speed sweep | `results_tables.md` Table 4 |
| Table 17 (Appendix B), cost decomposition | `results_tables.md` Table 9 |
| Fig. 1, campaign gallery | `experiments/figures/fig8_campaigns.png` (`exp_figures_maps.py`) |
| Fig. 2, solved plans | `experiments/figures/fig9_example_plan.png` (`exp_figures_maps.py`) |
| Fig. 3, convergence GA vs random search | `experiments/figures/fig1_convergence.png` |
| Fig. 4, ablation bars | `experiments/figures/fig2_ablation.png` |
| Fig. 5, fleet composition | `experiments/figures/fig7_fleet.png` |
| Fig. 6, operators on the tour subproblem | `experiments/figures/fig5_tsp_operators.png` |
| Fig. 7, truck-speed sweep | `experiments/figures/fig4_transit.png` |
| Fig. 8, two-stage planner vs joint GA | `experiments/figures/fig6_nn_hybrid.png` |

Campaign names in the result files are `C2close`, `C2far`, `C3line`, `C3tri`, `C3big`, `C5mixed`, `C5holes` (C5-obstacles in the paper), `C5varied`, `C5size`, `C10grid`, `C15scatter`; the control variants with the road on the north side of every second field carry the suffix `R`.

### Result record format

Each line of `exp_results.jsonl`, `exp_roadside.jsonl` and `exp_ga_exact.jsonl` is one run:

| Field | Meaning |
|---|---|
| `role`, `campaign_id`, `seed` | Campaign name, its database id, random seed |
| `method` | `ga` joint GA, `rs` random search, `ga_nn` two-stage with the nearest-neighbour tour, `ga_exact` two-stage with the exact tour |
| `crossover`, `mutation` | Operators on the order gene (`ox`, `pmx`, `cx` × `swap`, `insert`, `inversion`) or `rk` for the random-keys encoding |
| `ablation` | `full`, or the frozen dimension (`fixed_order`, `fixed_direction`, `fixed_start`, `fixed_dir_start`, `fixed_drones`), or a campaign-wide shared value (`single_direction`, `single_start`, `single_drones`) |
| `truck_speed` | `null` for the canonical 40 km/h, otherwise the speed of the sweep |
| `ngen`, `pop`, `n_evals`, `wall_s` | Budget (40 generations × 50 individuals) and wall-clock time |
| `best_fit`, `curve` | Best cost in $ and the best-so-far curve per generation |
| `final` | Components of the best plan: `drone_price` (wear), `salary` (crew), `penalty`, `time` (campaign duration, h), `transit_time` (h), `starts` (launches), `grid_total`/`grid_missed` (coverage check), `drone_usage` (flights and hours per drone id) |
| `best_order`, `best_ind` | Visit order and the full chromosome: order gene, per-field directions, start corners, drone sequences and truck-stop ratios |

Drone ids in `drone_usage` and `best_ind.drones` are database ids (223–227 in the shipped files, scout to heavy). The analysis scripts resolve them against the fleet in the current database, so the shipped files and freshly produced runs can both be analysed.

## Web application

The Django application visualizes fields, obstacles, roads and the resulting routes, and exports waypoints as CSV, MAVLink plan files or images.

```bash
python manage.py generate_drones     # sample fleet
python manage.py runserver
```

Docker: `docker-compose up --build`.

## Earlier work on this system

1. R. I. Mukhamediev, K. Yakunin, M. Aubakirov, I. Assanov, Y. Kuchin, A. Symagulov, V. Levashenko, E. Zaitseva, D. Sokolov, and Y. Amirgaliyev, "Coverage path planning optimization of heterogeneous UAVs group for precision agriculture," *IEEE Access*, vol. 11, pp. 5789–5803, 2023, doi: [10.1109/ACCESS.2023.3235207](https://doi.org/10.1109/ACCESS.2023.3235207).
2. K. Yakunin, V. Levashenko, E. Zaitseva, S. Chernyi, and R. I. Mukhamediev, "An algorithm for planning coverage of an area with obstacles with a heterogeneous group of drones using a genetic algorithm and parameterized polygon decomposition," *Drones*, vol. 9, no. 9, Art. no. 658, 2025, doi: [10.3390/drones9090658](https://doi.org/10.3390/drones9090658).

## Citation

```bibtex
@unpublished{yakunin2026multifield,
  author = {Yakunin, Kirill and Levashenko, Vitaly and Zaitseva, Elena and Cherny, Sergey and Mukhamediev, Ravil I.},
  title  = {Multi-Field Coverage Path Planning for a Truck-Carried Heterogeneous {UAV} Fleet: Joint Genetic Optimization Versus a Two-Stage Planner},
  note   = {Manuscript submitted to IEEE Access},
  year   = {2026}
}
```

Corresponding author: Kirill Yakunin, yakuninkirill671@gmail.com.
