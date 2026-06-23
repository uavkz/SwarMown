# Multi-Field Experiment Results (auto-generated)

## Table 1 — Joint GA vs Random Search (matched eval budget)

| Campaign | N | GA best_fit | RS best_fit | GA improv. | p (MWU) | GA cover | RS cover |
|---|---|---|---|---|---|---|---|
| C2close | 2 | 319.4 ± 2.7 | 335.9 ± 7.6 | +4.9% | 0.00016 *** | 100% | 100% |
| C2far | 2 | 330.4 ± 2.7 | 346.9 ± 7.6 | +4.8% | 0.00016 *** | 100% | 100% |
| C3line | 3 | 489.8 ± 4.6 | 567.0 ± 22.5 | +13.6% | 0.00016 *** | 100% | 100% |
| C3tri | 3 | 504.1 ± 6.4 | 577.0 ± 18.7 | +12.6% | 0.00016 *** | 100% | 100% |
| C5holes | 5 | 2000.9 ± 34.0 | 2438.0 ± 55.0 | +17.9% | 0.00016 *** | 100% | 100% |
| C5mixed | 5 | 1100.6 ± 39.0 | 1404.8 ± 52.3 | +21.7% | 0.00016 *** | 100% | 100% |
| C5varied | 5 | 592.0 ± 27.4 | 833.6 ± 38.4 | +29.0% | 0.00016 *** | 100% | 100% |
| C10grid | 10 | 3184.5 ± 47.7 | 3752.2 ± 106.0 | +15.1% | 0.00016 *** | 100% | 100% |

## Table 2 — Ablation: cost increase when a dimension is disabled

Positive Δ% = disabling that dimension makes the solution *worse* (so that dimension matters).

| Campaign | full | fixed_order | single_direction | single_start | single_drones |
|---|---|---|---|---|---|
| C3line | 489.8 (base) | +0.1% ns | -0.8% ns | +0.3% ns | +0.4% ns |
| C5mixed | 1100.6 (base) | -3.0% ** | -2.9% ** | -1.0% ns | -1.8% ns |
| C5holes | 2000.9 (base) | +1.7% ns | +2.8% ** | +2.6% * | +2.4% * |
| C10grid | 3184.5 (base) | -3.1% ** | -6.3% *** | +0.6% ns | +4.1% ** |
| C5varied | 592.0 (base) | -5.5% * | +7.0% ** | +2.1% ns | -1.2% ns |

## Table 3 — Scaling with number of fields (canonical GA: full, OX+swap)

| Campaign | N | best_fit | wall (s) | transit (h) | coverage | GA order-gap vs opt |
|---|---|---|---|---|---|---|
| C2close | 2 | 319.4 ± 2.7 | 86.6 | 0.01 | 100% | 0.0% |
| C2far | 2 | 330.4 ± 2.7 | 88.5 | 1.11 | 100% | 0.0% |
| C3line | 3 | 489.8 ± 4.6 | 184.8 | 1.00 | 100% | 0.0% |
| C3tri | 3 | 504.1 ± 6.4 | 185.5 | 1.23 | 100% | 0.0% |
| C5holes | 5 | 2000.9 ± 34.0 | 587.7 | 0.51 | 100% | 19.2% |
| C5mixed | 5 | 1100.6 ± 39.0 | 276.1 | 1.40 | 100% | 4.5% |
| C5varied | 5 | 592.0 ± 27.4 | 292.5 | 0.43 | 100% | 38.8% |
| C10grid | 10 | 3184.5 ± 47.7 | 517.9 | 0.81 | 100% | 47.6% |

## Table 4 — Truck-speed sensitivity (full GA, OX+swap)

| Campaign | truck km/h | best_fit | transit (h) | GA order-gap vs opt |
|---|---|---|---|---|
| C5mixed | 20 | 1252.0 ± 20.6 | 2.78 | 3.5% |
| C5mixed | 40 | 1100.6 ± 39.0 | 1.40 | 4.5% |
| C5mixed | 60 | 1036.3 ± 18.0 | 0.97 | 8.7% |
| C5mixed | 80 | 1009.7 ± 17.7 | 0.72 | 7.1% |
| C10grid | 40 | 3184.5 ± 47.7 | 0.81 | 47.6% |

## Table 5 — Ordering operators: joint cost (C10grid) vs TSP-subproblem gap

Joint best_fit barely moves (ordering is a minor cost lever); the TSP gap is the honest signal.

| Operator | C10grid joint best_fit | C10grid TSP gap% | C5* TSP gap% |
|---|---|---|---|
| ox_swap | 3184.5 ± 47.7 | 10.17% | 1.74% |
| ox_insert | 3145.9 ± 45.3 | 6.34% | 0.13% |
| ox_inversion | 3159.6 ± 63.7 | 2.22% | 1.75% |
| pmx_swap | 3220.6 ± 48.0 | 13.56% | 1.70% |
| pmx_insert | 3170.5 ± 39.3 | 8.42% | 0.13% |
| pmx_inversion | 3216.6 ± 55.7 | 3.93% | 2.11% |
| cx_swap | 3226.2 ± 80.1 | 19.44% | 4.30% |
| cx_insert | 3229.9 ± 11.0 | 10.60% | 0.62% |
| cx_inversion | 3172.3 ± 55.4 | 4.24% | 2.05% |

## Table 6 — Field-ordering: heuristics vs exact optimum (transit hours)

| Campaign | N | optimal | nearest-nbr (gap) | default (gap) | worst |
|---|---|---|---|---|---|
| C2close | 2 | 0.010 | 0.010 (0%) | 0.010 (0%) | 0.060 |
| C2far | 2 | 1.114 | 1.114 (0%) | 1.114 (0%) | 1.163 |
| C3line | 3 | 1.001 | 1.001 (0%) | 1.001 (0%) | 2.032 |
| C3tri | 3 | 1.228 | 1.242 (1%) | 1.242 (1%) | 1.278 |
| C5holes | 5 | 0.427 | 0.427 (0%) | 0.518 (21%) | 0.966 |
| C5mixed | 5 | 1.341 | 1.405 (5%) | 1.407 (5%) | 2.839 |
| C5varied | 5 | 0.310 | 0.340 (10%) | 0.350 (13%) | 0.583 |
| C10grid | 10 | 0.550 | 0.634 (15%) | 0.674 (23%) | 1.816 |

## Table 7 — NN-seeded hybrid vs plain joint GA (full, OX+swap)

Seeding the initial order with nearest-neighbour fixes the GA's neglected ordering at no extra budget.

| Campaign | N | GA best_fit | NN-GA best_fit | Δ cost | GA order-gap | NN-GA order-gap |
|---|---|---|---|---|---|---|
| C5mixed | 5 | 1100.6 ± 39.0 | 1085.2 ± 23.3 | -1.4% | 4.5% | 4.8% |
| C5holes | 5 | 2000.9 ± 34.0 | 2035.8 ± 26.8 | +1.7% | 19.2% | 0.0% |
| C10grid | 10 | 3184.5 ± 47.7 | 3135.1 ± 50.6 | -1.5% | 47.6% | 15.3% |
| C5varied | 5 | 592.0 ± 27.4 | 559.1 ± 22.2 | -5.6% | 38.8% | 9.5% |
