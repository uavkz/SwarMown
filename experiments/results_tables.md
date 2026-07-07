# Multi-Field Experiment Results (auto-generated)

## Table 1 — Joint GA vs Random Search (matched eval budget)

| Campaign | N | GA best_fit | RS best_fit | GA improv. | p (MWU) | GA cover | RS cover |
|---|---|---|---|---|---|---|---|
| C2close | 2 | 28.2 ± 0.6 | 29.4 ± 0.6 | +4.2% | 0.003 ** | 100% | 100% |
| C2far | 2 | 39.0 ± 0.2 | 40.7 ± 0.5 | +4.0% | 0.00016 *** | 100% | 100% |
| C3big | 3 | 227.2 ± 43.6 | 250.6 ± 26.2 | +9.3% | 0.13 ns | 100% | 100% |
| C3line | 3 | 52.3 ± 1.4 | 57.1 ± 1.2 | +8.3% | 0.00016 *** | 100% | 100% |
| C3tri | 3 | 56.8 ± 3.2 | 58.8 ± 0.9 | +3.4% | 0.065 ns | 100% | 100% |
| C5holes | 5 | 154.2 ± 24.7 | 212.6 ± 25.8 | +27.5% | 0.00062 *** | 100% | 100% |
| C5mixed | 5 | 108.9 ± 26.4 | 125.9 ± 10.1 | +13.5% | 0.13 ns | 100% | 100% |
| C5size | 5 | 101.3 ± 17.5 | 121.0 ± 12.4 | +16.3% | 0.05 * | 100% | 100% |
| C5varied | 5 | 59.2 ± 2.2 | 78.0 ± 14.5 | +24.1% | 0.00016 *** | 100% | 100% |
| C10grid | 10 | 415.6 ± 36.5 | 680.8 ± 76.6 | +39.0% | 0.00016 *** | 100% | 100% |
| C15scatter | 15 | 447.8 ± 77.9 | 756.3 ± 37.0 | +40.8% | 0.00016 *** | 100% | 100% |

## Table 2 — Ablation: cost increase when a dimension is disabled

Positive Δ% = disabling that dimension makes the solution *worse* (so that dimension matters).

| Campaign | full | fixed_order | single_direction | single_start | single_drones |
|---|---|---|---|---|---|
| C3line | 52.3 (base) | +1.3% ns | +2.8% * | +0.7% ns | -2.3% * |
| C5mixed | 108.9 (base) | -18.0% ns | -18.9% ns | -13.5% ns | -22.8% * |
| C5holes | 154.2 (base) | +15.3% ns | +0.1% ns | +3.1% ns | -18.4% *** |
| C10grid | 415.6 (base) | -4.9% ns | +3.5% ns | +4.2% ns | -45.7% *** |
| C5varied | 59.2 (base) | +16.9% ns | +18.1% ** | -0.5% ns | -3.0% ns |
| C5size | 101.3 (base) | -1.5% ns | -8.1% ns | +2.0% ns | -18.0% *** |
| C3big | 227.2 (base) | -8.5% ns | -14.2% ns | -10.9% ns | -15.4% ns |

## Table 3 — Scaling with number of fields (canonical GA: full, OX+inversion)

| Campaign | N | best_fit | wall (s) | total time (h) | transit (h) | soft pen. % of cost | coverage | GA order-gap vs opt |
|---|---|---|---|---|---|---|---|---|
| C2close | 2 | 28.2 ± 0.6 | 65.1 | 1.97 | 0.01 | 0.0% | 100% | 0.0% |
| C2far | 2 | 39.0 ± 0.2 | 64.6 | 3.08 | 1.11 | 0.0% | 100% | 0.0% |
| C3big | 3 | 227.2 ± 43.6 | 555.4 | 8.93 | 0.21 | 15.9% | 100% | 0.0% |
| C3line | 3 | 52.3 ± 1.4 | 120.4 | 3.88 | 0.99 | 0.0% | 100% | 0.0% |
| C3tri | 3 | 56.8 ± 3.2 | 126.8 | 4.30 | 1.23 | 0.0% | 100% | 0.4% |
| C5holes | 5 | 154.2 ± 24.7 | 470.0 | 7.89 | 0.48 | 1.2% | 100% | 17.2% |
| C5mixed | 5 | 108.9 ± 26.4 | 225.4 | 6.36 | 1.33 | 0.0% | 100% | 0.7% |
| C5size | 5 | 101.3 ± 17.5 | 231.8 | 5.73 | 0.37 | 0.0% | 100% | 4.5% |
| C5varied | 5 | 59.2 ± 2.2 | 202.6 | 3.89 | 0.34 | 0.0% | 100% | 8.7% |
| C10grid | 10 | 415.6 ± 36.5 | 458.1 | 11.40 | 0.84 | 36.0% | 100% | 57.4% |
| C15scatter | 15 | 447.8 ± 77.9 | 274.2 | 10.39 | 2.07 | 28.4% | 100% | 47.9% |

## Table 4 — Truck-speed sensitivity (full GA, OX+inversion)

| Campaign | truck km/h | best_fit | transit (h) | GA order-gap vs opt |
|---|---|---|---|---|
| C5mixed | 20 | 108.4 ± 10.1 | 2.70 | 2.2% |
| C5mixed | 40 | 108.9 ± 26.4 | 1.33 | 0.7% |
| C5mixed | 60 | 90.1 ± 19.1 | 0.91 | 3.6% |
| C5mixed | 80 | 83.6 ± 8.4 | 0.71 | 7.5% |
| C10grid | 20 | 494.3 ± 33.8 | 1.46 | 36.2% |
| C10grid | 40 | 415.6 ± 36.5 | 0.84 | 57.4% |
| C10grid | 60 | 414.4 ± 27.4 | 0.56 | 57.1% |
| C10grid | 80 | 382.1 ± 61.7 | 0.52 | 95.3% |

## Table 5 — Ordering operators: joint cost (C10grid) vs TSP-subproblem gap

Joint-cost column: n=8 seeds for ox_inversion (canonical) and rk, n=3 for the other operator pairs (robustness check only); TSP gaps are 30 repetitions each. C5* = mean over C5mixed, C5holes, C5size.

| Operator | C10grid joint best_fit | C10grid TSP gap% | C15 TSP gap% | C5* TSP gap% |
|---|---|---|---|---|
| ox_swap | 398.8 ± 100.2 | 12.93% | 16.84% | 1.13% |
| ox_insert | 479.6 ± 34.8 | 6.45% | 16.11% | 0.34% |
| ox_inversion | 415.6 ± 36.5 | 4.70% | 9.05% | 1.66% |
| pmx_swap | 446.2 ± 3.7 | 13.98% | 20.33% | 1.50% |
| pmx_insert | 441.4 ± 3.6 | 7.37% | 14.77% | 0.22% |
| pmx_inversion | 388.5 ± 63.4 | 6.60% | 9.93% | 1.66% |
| cx_swap | 371.8 ± 92.9 | 15.58% | 20.35% | 2.99% |
| cx_insert | 355.9 ± 104.0 | 7.54% | 21.78% | 0.48% |
| cx_inversion | 441.6 ± 22.4 | 5.07% | 14.24% | 2.37% |
| rk | 438.0 ± 20.7 | 9.79% | 18.80% | 0.28% |

## Table 5b — Order encoding on the joint problem: permutation (OX+inversion) vs random keys

| Campaign | N | perm best_fit | rk best_fit | Δ | p (MWU) | perm order-gap | rk order-gap |
|---|---|---|---|---|---|---|---|
| C10grid | 10 | 415.6 ± 36.5 | 438.0 ± 20.7 | +5.4% | 0.33 ns | 57.4% | 61.4% |
| C15scatter | 15 | 447.8 ± 77.9 | 469.4 ± 69.3 | +4.8% | 0.28 ns | 47.9% | 57.2% |

## Table 6 — Field-ordering: heuristics vs exact optimum (transit hours)

| Campaign | N | optimal | nearest-nbr (gap) | default (gap) | worst |
|---|---|---|---|---|---|
| C2close | 2 | 0.010 | 0.010 (0%) | 0.010 (0%) | 0.060 |
| C2far | 2 | 1.114 | 1.114 (0%) | 1.114 (0%) | 1.163 |
| C3big | 3 | 0.209 | 0.209 (0%) | 0.209 (0%) | 0.353 |
| C3line | 3 | 0.989 | 0.989 (0%) | 0.989 (0%) | 2.038 |
| C3tri | 3 | 1.225 | 1.235 (1%) | 1.235 (1%) | 1.285 |
| C5holes | 5 | 0.410 | 0.410 (0%) | 0.492 (20%) | 0.968 |
| C5mixed | 5 | 1.321 | 1.394 (6%) | 1.397 (6%) | 2.847 |
| C5size | 5 | 0.357 | 0.357 (0%) | 0.360 (1%) | 0.690 |
| C5varied | 5 | 0.310 | 0.340 (10%) | 0.350 (13%) | 0.583 |
| C10grid | 10 | 0.535 | 0.638 (19%) | 0.618 (16%) | 1.842 |
| C15scatter | 15 | 1.403 | 1.546 (10%) | 1.892 (35%) | 4.724 |

## Table 7 — NN-fixed hybrid vs plain joint GA (full, OX+inversion, matched budget)

The hybrid freezes the order gene at the nearest-neighbour tour and spends the whole (identical) evaluation budget on the per-field coverage parameters.

| Campaign | N | GA best_fit | NN-GA best_fit | Δ cost | p (MWU) | GA order-gap | NN-GA order-gap |
|---|---|---|---|---|---|---|---|
| C5mixed | 5 | 108.9 ± 26.4 | 87.1 ± 4.9 | -20.1% | 0.16 ns | 0.7% | 5.5% |
| C5holes | 5 | 154.2 ± 24.7 | 134.2 ± 14.9 | -13.0% | 0.028 * | 17.2% | 0.0% |
| C10grid | 10 | 415.6 ± 36.5 | 400.9 ± 63.5 | -3.6% | 0.23 ns | 57.4% | 19.3% |
| C5varied | 5 | 59.2 ± 2.2 | 60.9 ± 3.5 | +2.9% | 0.33 ns | 8.7% | 9.5% |
| C5size | 5 | 101.3 ± 17.5 | 90.2 ± 6.3 | -10.9% | 0.13 ns | 4.5% | 0.0% |
| C15scatter | 15 | 447.8 ± 77.9 | 390.1 ± 53.0 | -12.9% | 0.1 ns | 47.9% | 10.2% |

## Table 8 — Fleet composition of the best plans (canonical GA, mean over seeds)

Share of flights performed by each airframe; |D| = distinct airframes used.

| Campaign | N | |D| | Phantom 4 | Mavic 2 | Autel Evo II | Matrice 300 | Mini 4 Pro |
|---|---|---|---|---|---|---|---|
| C2close | 2 | 1.0 | 12% | 0% | 0% | 0% | 88% |
| C2far | 2 | 1.0 | 0% | 0% | 0% | 0% | 100% |
| C3big | 3 | 1.5 | 18% | 33% | 12% | 12% | 24% |
| C3line | 3 | 1.0 | 38% | 0% | 0% | 0% | 62% |
| C3tri | 3 | 1.0 | 0% | 12% | 0% | 0% | 88% |
| C5holes | 5 | 1.2 | 14% | 41% | 25% | 12% | 8% |
| C5mixed | 5 | 1.2 | 32% | 0% | 25% | 0% | 42% |
| C5size | 5 | 1.2 | 38% | 31% | 0% | 0% | 31% |
| C5varied | 5 | 1.0 | 25% | 0% | 0% | 0% | 75% |
| C10grid | 10 | 1.9 | 38% | 18% | 5% | 0% | 40% |
| C15scatter | 15 | 2.4 | 23% | 19% | 12% | 3% | 42% |
