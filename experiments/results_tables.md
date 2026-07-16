# Multi-Field Experiment Results (auto-generated)

## Table 1 — Joint GA vs Random Search (matched eval budget)

| Campaign | N | GA best_fit | RS best_fit | GA improv. | p (MWU) | GA cover | RS cover |
|---|---|---|---|---|---|---|---|
| C2close | 2 | 31.7 ± 0.2 | 33.0 ± 0.3 | +4.0% | 0.00016 *** | 100% | 100% |
| C2far | 2 | 42.7 ± 0.1 | 44.3 ± 0.2 | +3.5% | 0.00016 *** | 100% | 100% |
| C3big | 3 | 122.7 ± 4.5 | 137.2 ± 4.3 | +10.5% | 0.00062 *** | 100% | 100% |
| C3line | 3 | 56.8 ± 0.3 | 61.5 ± 0.5 | +7.5% | 0.00016 *** | 100% | 100% |
| C3tri | 3 | 60.6 ± 0.1 | 63.4 ± 0.4 | +4.5% | 0.00016 *** | 100% | 100% |
| C5holes | 5 | 119.0 ± 1.1 | 136.4 ± 1.8 | +12.8% | 0.00016 *** | 100% | 100% |
| C5mixed | 5 | 94.1 ± 1.1 | 105.2 ± 1.7 | +10.6% | 0.00016 *** | 100% | 100% |
| C5size | 5 | 85.9 ± 0.4 | 95.0 ± 0.9 | +9.6% | 0.00016 *** | 100% | 100% |
| C5varied | 5 | 64.6 ± 1.6 | 73.7 ± 0.7 | +12.4% | 0.00016 *** | 100% | 100% |
| C10grid | 10 | 261.2 ± 2.9 | 338.2 ± 13.1 | +22.8% | 0.00016 *** | 100% | 100% |
| C15scatter | 15 | 226.8 ± 7.6 | 313.2 ± 4.7 | +27.6% | 0.00016 *** | 100% | 100% |

## Table 2 — Ablation: cost increase when a dimension is not optimized

Each dimension frozen at a reasonable default. Positive Δ% = freezing hurts (the dimension matters).

| Campaign | full | fixed order | fixed direction | fixed start corner | fixed drone (mid-class) |
|---|---|---|---|---|---|
| C3line | 56.8 (base) | -0.2% ns | +2.7% *** | +0.3% ns | +3.1% *** |
| C5mixed | 94.1 (base) | -0.6% ns | +3.0% *** | -0.5% ns | +2.4% ** |
| C5holes | 119.0 (base) | -1.3% ns | -1.1% * | +0.8% ns | +0.5% ns |
| C10grid | 261.2 (base) | -4.6% *** | +2.1% * | +0.2% ns | -0.7% ns |
| C5varied | 64.6 (base) | -0.6% ns | +9.0% *** | +1.0% ns | +3.1% * |
| C5size | 85.9 (base) | +0.9% ns | +2.5% *** | +1.0% ns | +3.4% *** |
| C3big | 122.7 (base) | -1.2% ns | -1.8% ns | -0.8% ns | +86.0% *** |
| C15scatter | 226.8 (base) | -2.2% ns | -2.9% ns | -0.6% ns | +4.6% * |

## Table 2b — Granularity: shared campaign-wide value vs per-field values

Dimension still optimized but shared across fields. Positive Δ% = per-field variation matters.

| Campaign | full | shared direction | shared start corner | shared drone sequence |
|---|---|---|---|---|
| C5size | 85.9 (base) | +1.9% *** | +0.4% ns | +1.3% ** |
| C5holes | 119.0 (base) | -1.2% ns | -1.2% ns | +0.1% ns |
| C10grid | 261.2 (base) | -1.6% ns | -1.0% ns | -2.4% * |

## Table 3 — Scaling with number of fields (canonical GA: full, OX+inversion)

| Campaign | N | best_fit | wall (s) | total time (h) | transit (h) | soft pen. % of cost | coverage | GA order-gap vs opt |
|---|---|---|---|---|---|---|---|---|
| C2close | 2 | 31.7 ± 0.2 | 89.1 | 1.95 | 0.01 | 0.0% | 100% | 0.0% |
| C2far | 2 | 42.7 ± 0.1 | 89.9 | 3.05 | 1.11 | 0.0% | 100% | 0.0% |
| C3big | 3 | 122.7 ± 4.5 | 839.2 | 6.64 | 0.21 | 0.0% | 100% | 2.4% |
| C3line | 3 | 56.8 ± 0.3 | 274.6 | 3.86 | 0.99 | 0.0% | 100% | 0.0% |
| C3tri | 3 | 60.6 ± 0.1 | 281.1 | 4.21 | 1.23 | 0.0% | 100% | 0.0% |
| C5holes | 5 | 119.0 ± 1.1 | 735.0 | 7.29 | 0.45 | 0.0% | 100% | 9.9% |
| C5mixed | 5 | 94.1 ± 1.1 | 413.4 | 6.29 | 1.38 | 0.0% | 100% | 4.3% |
| C5size | 5 | 85.9 ± 0.4 | 418.3 | 5.34 | 0.39 | 0.0% | 100% | 8.1% |
| C5varied | 5 | 64.6 ± 1.6 | 384.8 | 3.82 | 0.32 | 0.0% | 100% | 4.8% |
| C10grid | 10 | 261.2 ± 2.9 | 719.7 | 10.93 | 0.80 | 32.8% | 100% | 48.9% |
| C15scatter | 15 | 226.8 ± 7.6 | 478.9 | 9.92 | 1.90 | 24.2% | 100% | 35.7% |

## Table 4 — Truck-speed sensitivity (full GA, OX+inversion)

| Campaign | truck km/h | best_fit | transit (h) | GA order-gap vs opt |
|---|---|---|---|---|
| C5mixed | 20 | 107.5 ± 1.3 | 2.68 | 1.4% |
| C5mixed | 40 | 94.1 ± 1.1 | 1.38 | 4.3% |
| C5mixed | 60 | 89.3 ± 0.7 | 0.92 | 4.3% |
| C5mixed | 80 | 87.3 ± 1.1 | 0.70 | 6.3% |
| C10grid | 20 | 287.5 ± 6.9 | 1.26 | 18.1% |
| C10grid | 40 | 261.2 ± 2.9 | 0.80 | 48.9% |
| C10grid | 60 | 248.3 ± 4.5 | 0.56 | 56.7% |
| C10grid | 80 | 243.7 ± 5.5 | 0.43 | 60.9% |

## Table 5 — Ordering operators: joint cost (C10grid) vs TSP-subproblem gap

Joint-cost column: n=8 seeds for ox_inversion (canonical) and rk, n=3 for the other operator pairs (robustness check only); TSP gaps are 30 repetitions each. C5* = mean over C5mixed, C5holes, C5size.

| Operator | C10grid joint best_fit | C10grid TSP gap% | C15 TSP gap% | C5* TSP gap% |
|---|---|---|---|---|
| ox_swap | 259.6 ± 1.8 | 12.93% | 16.84% | 1.13% |
| ox_insert | 261.9 ± 5.8 | 6.45% | 16.11% | 0.34% |
| ox_inversion | 261.2 ± 2.9 | 4.70% | 9.05% | 1.66% |
| pmx_swap | 261.2 ± 1.2 | 13.98% | 20.33% | 1.50% |
| pmx_insert | 264.0 ± 5.5 | 7.37% | 14.77% | 0.22% |
| pmx_inversion | 260.0 ± 2.4 | 6.60% | 9.93% | 1.66% |
| cx_swap | 265.9 ± 1.7 | 15.58% | 20.35% | 2.99% |
| cx_insert | 266.6 ± 5.1 | 7.54% | 21.78% | 0.48% |
| cx_inversion | 273.5 ± 3.1 | 5.07% | 14.24% | 2.37% |
| rk | 265.4 ± 7.3 | 9.79% | 18.80% | 0.28% |

## Table 5b — Order encoding on the joint problem: permutation (OX+inversion) vs random keys

| Campaign | N | perm best_fit | rk best_fit | Δ | p (MWU) | perm order-gap | rk order-gap |
|---|---|---|---|---|---|---|---|
| C10grid | 10 | 261.2 ± 2.9 | 265.4 ± 7.3 | +1.6% | 0.13 ns | 48.9% | 52.6% |
| C15scatter | 15 | 226.8 ± 7.6 | 231.1 ± 7.6 | +1.9% | 0.28 ns | 35.7% | 42.6% |

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
| C5mixed | 5 | 94.1 ± 1.1 | 93.4 ± 0.6 | -0.8% | 0.38 ns | 4.3% | 5.5% |
| C5holes | 5 | 119.0 ± 1.1 | 117.5 ± 1.1 | -1.3% | 0.038 * | 9.9% | 0.0% |
| C10grid | 10 | 261.2 ± 2.9 | 250.3 ± 3.3 | -4.2% | 0.00016 *** | 48.9% | 19.3% |
| C5varied | 5 | 64.6 ± 1.6 | 64.8 ± 1.5 | +0.4% | 0.88 ns | 4.8% | 9.5% |
| C5size | 5 | 85.9 ± 0.4 | 85.9 ± 0.3 | +0.0% | 0.72 ns | 8.1% | 0.0% |
| C15scatter | 15 | 226.8 ± 7.6 | 207.3 ± 2.6 | -8.6% | 0.00016 *** | 35.7% | 10.2% |

## Table 8 — Fleet composition of the best plans (canonical GA, mean over seeds)

Share of flights performed by each airframe; |D| = distinct airframes used.

| Campaign | N | |D| | Scout (Mini-class) | Light (Phantom-class) | Mid (Mavic-class) | Long (Evo-class) | Heavy (M300-class) |
|---|---|---|---|---|---|---|---|
| C2close | 2 | 1.0 | 0% | 100% | 0% | 0% | 0% |
| C2far | 2 | 1.0 | 0% | 100% | 0% | 0% | 0% |
| C3big | 3 | 3.1 | 12% | 52% | 23% | 12% | 0% |
| C3line | 3 | 1.1 | 4% | 96% | 0% | 0% | 0% |
| C3tri | 3 | 1.0 | 0% | 100% | 0% | 0% | 0% |
| C5holes | 5 | 3.1 | 18% | 49% | 31% | 2% | 0% |
| C5mixed | 5 | 1.6 | 8% | 85% | 8% | 0% | 0% |
| C5size | 5 | 2.8 | 38% | 45% | 15% | 2% | 0% |
| C5varied | 5 | 2.0 | 30% | 70% | 0% | 0% | 0% |
| C10grid | 10 | 3.2 | 24% | 46% | 26% | 4% | 0% |
| C15scatter | 15 | 3.4 | 42% | 44% | 10% | 3% | 0% |
