# Multi-Field UAV Coverage Campaigns: Joint Ordering + Per-Field Optimization

> **STALE (2026-07-03): all numbers below predate two model fixes** — (1) campaign time
> is now the sum of per-field makespans + transit (was: max over drones across fields,
> which let flights at different fields overlap); (2) drone `price_per_kilometer` is now
> applied to km (was: to meters, inflating wear cost ×1000 and with it the
> "ordering is a minor lever" conclusion). Canonical operator is now ox+inversion,
> GA/RS random streams are independent, the NN hybrid is described as NN-*fixed*
> (order frozen), day limits are 8/14 h. Additionally (2026-07-07) all campaigns except
> the C2 controls were rebuilt with realistic irregular parcels (rotated quad/trapezoid/
> pentagon/wedge/L-shape templates, area-matched) and the matrix fully re-run again;
> this file is superseded by the regenerated `results_tables.md` and the paper draft in
> `experiments/paper/`. Old raw data: `experiments/archive/` (square-fields run:
> `exp_results_square_fields.jsonl`).

*Results for the multi-field track. All numbers are regenerable: `scripts/exp_campaigns.py`
→ `scripts/exp_run.py` → `scripts/exp_analyze.py`. Canonical tables live in
`experiments/results_tables.md`, machine-readable aggregates in `results_summary.json`,
figures in `experiments/figures/`. Headline settings: GA `pop=50, ngen=40`, tournament(3),
cxpb 0.5, mutpb 1; 8 seeds per configuration; significance by two-sided Mann–Whitney U.*

---

## 1. Problem & contribution

A truck carries a set of UAVs and visits a sequence of agricultural **fields**. At each field
the swarm flies a zamboni coverage pattern, launching/landing from truck stops on a road beside
the field; between fields the truck **drives** (transit). We jointly optimize:

- **field visit order** — an open-path (no return-to-depot) sequencing problem over the fields;
- **per-field coverage parameters** — flight-line direction, start corner, the subset of drones
  used, and truck-stop positions along that field's road.

This extends the single-field planner (and the 2D/3D obstacle tracks) to a **campaign** scale; the
novelty is the *joint* GA co-optimizing a discrete permutation (the tour) with the per-field
coverage knobs under one campaign-level cost.

**Cost structure (the key fact).** Each field is routed independently, so per-drone cumulative
flight time (a sum) and drone price are **order-invariant**. Field ordering influences total cost
through exactly one channel: truck **transit time**, which enters `total_time = max_drone_time +
transit` and hence salary (`hourly_price · total_time · n_drones`). Everything below follows from
this: *coverage parameters set the cost level; ordering is a secondary lever whose value scales
with the transit-to-coverage ratio.*

## 2. Experimental setup

**Campaigns** (`scripts/exp_campaigns.py` + `exp_campaign_varied.py`, deterministic). Eight
campaigns near Astana, KZ; shared grid_step 200 m, truck 40 km/h, 3 varied drones (DJI Phantom 4 /
Mavic 2 / Autel Evo II), start_price \$3, hourly \$10.

| role | N | geometry | purpose |
|---|---|---|---|
| C2close | 2 | adjacent (~1.4 km) | transit negligible |
| C2far | 2 | ~45 km apart | transit dominates |
| C3line | 3 | collinear, gaps 2.8 / 39 km | default order already optimal |
| C3tri | 3 | equidistant triangle | ordering irrelevant by symmetry |
| C5mixed | 5 | two close clusters + one far | grouping matters |
| C5holes | 5 | varied sizes, 3 fields with holes | obstacle decomposition + ordering |
| C5varied | 5 | elongated fields, 5 orientations | per-field **direction** matters |
| C10grid | 10 | 2×5 grid | scaling; real combinatorial tour |

**Methods.** *Joint GA* (DEAP) with OX/PMX/CX order crossover and swap/insert/inversion order
mutation, per-field uniform-swap crossover and per-gene mutation. *Random search (RS)* baseline:
same budget (`pop·ngen = 2000` evaluations), keep best. *Default-order* and *single-dimension*
baselines are the GA ablations. *NN-seeded hybrid* (`ga_nn`): GA whose initial population's order
gene is the nearest-neighbour tour. The GA has no elitism, so we report best-of-run and a monotone
best-so-far convergence curve.

**Ordering ground truth.** Ordering acts only through the directed transit matrix, so we solve the
ordering subproblem **exactly** (Held–Karp open-path TSP, `scripts/exp_ordering.py`) and compare
to nearest-neighbour, default, and worst tours; `scripts/exp_tsp_operators.py` benchmarks the
ordering operators against this optimum.

## 3. Results

### 3.1 The joint GA beats matched-budget random search everywhere (Table 1, Fig 1)
On all seven base campaigns the GA dominates RS, from **+4.8%** (2-field, tiny search space) to
**+21.7%** (C5mixed); every comparison is significant (Mann–Whitney `p = 1.6e-4 ***`, the floor for
n=8 vs 8 — i.e. *perfect separation* of the two seed distributions). Both methods reach **100%
coverage** (penalty-free) on every run. The convergence curves (Fig 1) show the GA pulling clear of
RS by ~10 generations with non-overlapping ±SD bands on the larger campaigns.

### 3.2 What the cost actually comes from — ablation (Table 2, Fig 2)
Disabling one dimension at a time and measuring the cost change vs the full GA reveals a subtler
story than "everything helps." Several restrictions make the solution **significantly *better***
under the fixed budget:

- **`single_direction` −6.3%*** and `fixed_order` −3.1%** on C10grid; −2.9%\*\* / −3.0%\*\* on
  C5mixed.** When fields are near-square and co-oriented (C2–C10), per-field direction has almost
  no lever, and ordering has only a weak one. Searching those dimensions anyway **wastes a fixed
  budget** — every generation spent mutating the order/direction genes is a generation *not* spent
  refining the dominant coverage parameters. Collapsing a weak dimension shrinks the search space
  and the GA converges to a better cost.
- **`single_drones` +4.1%** on C10grid, +2.4%\* on C5holes.** Drone selection is a *real* lever
  that grows with N (more fields ⇒ more scope to assign the right drone), so disabling it hurts.
- **C5holes: all four dimensions ≥ +1.7% (three significant).** With obstacle decomposition every
  knob earns its place.
- **C5varied: `single_direction` +7.0%, the sign flips.** With elongated fields at five different
  orientations the per-field optimal direction differs field-to-field, so collapsing to a shared
  direction *hurts* by 7% — the exact opposite of the −6.3% on the square-field C10grid. This is
  the clean control: per-field direction optimization is worthless when fields are co-oriented and
  valuable when they are not. (On C5varied `fixed_order` is still −5.5% — ordering remains a weak
  lever even here — and `single_start` +2.1%.)

**Takeaway:** a dimension is worth optimizing only when it has *both* a real cost lever *and*
heterogeneity across fields. Otherwise, under a fixed budget, adding it to the joint search is net
harmful — a concrete argument for fixing weak dimensions (see §3.5).

### 3.3 The ordering subproblem: operators vs the exact optimum (Tables 5–6, Fig 5)
Against the Held–Karp optimum, all nine operator pairs are exact at N=3; **`insert` mutation is
best at N=5** (0.1% mean gap) and **`inversion` mutation is best at N=10** — `ox_inversion` reaches
**2.2%** gap vs `ox_swap`'s 10.2%, `pmx_swap`'s 13.6%, and `cx_swap`'s 19.4% (worst). OX/PMX
crossover beat CX, and `inversion` beats `swap`/`insert` for every crossover at N=10. In *joint* cost,
by contrast, the operator choice is within noise (C10grid best_fit spans only ~2.6% across all nine,
all overlapping) — because ordering is a minor cost lever. **Applied:** the order-mutation default
has been changed from `swap` to **`inversion`** (a 2-opt-like move) in `build_multi_argparser`
(`scripts/ga_multi_common.py`). The exact tours also bound the heuristics (Table 6): the *default* field order is
up to **23% above optimal** (C10grid) and **21%** (C5holes), while nearest-neighbour is ≤15%.

### 3.4 The GA optimizes ordering exactly as much as it pays (Tables 3–4)
Two independent measurements show the joint GA invests in ordering in proportion to the transit
share of cost:
- **Truck-speed sweep (Table 4, C5mixed):** as the truck slows 80→20 km/h, transit rises
  0.72→2.78 h and the GA's order-gap *shrinks* 7.1%→3.5% — when transit is expensive the fitness
  gradient on ordering is steep and the GA chases it; when transit is cheap it ignores ordering.
- **Scaling (Table 3):** the GA's order-gap grows 0% (N≤3) → 4.5% (C5mixed) → 19.2% (C5holes) →
  **47.6%** (C10grid). The tour space explodes as N! while the cost lever stays weak, so the joint
  GA increasingly leaves transit on the table.

This is the core empirical claim of the paper, and it sets up the fix.

### 3.5 NN-seeded hybrid (Table 7, Fig 6)
Fixing the order to the nearest-neighbour tour and spending the entire GA budget on the coverage
parameters removes the GA's ordering deficit at **zero extra evaluation cost**: the achieved
order-gap collapses from the joint GA's 38.8%→**9.5%** (C5varied), 47.6%→**15.3%** (C10grid),
19.2%→**0.0%** (C5holes). The cost effect tracks the transit share exactly as the thesis predicts:
- **C5varied −5.6%** and **C10grid −1.5%, C5mixed −1.4%** — wins where transit is a non-trivial
  share and/or the joint GA's ordering deficit was large;
- **C5holes +1.7% (ns)** — *neutral*, because here coverage cost (~2000) dwarfs transit (~0.43 h ≈
  \$12), so even perfecting the order (19.2%→0%) cannot move total cost; the small difference is
  param-search noise.

So the recommended planner is **NN-order + GA-on-coverage-params**: it never hurts beyond noise,
helps materially when ordering matters, and is strictly cheaper to run (smaller search space). This
also subsumes the `fixed_order` ablation finding (§3.2) — fixing the order is good; fixing it to a
*nearest-neighbour* order rather than the arbitrary default is strictly better on transit.

### 3.6 Scaling & runtime (Table 3)
Wall-clock per run grows with the work: ~87 s (N=2) → ~518 s (N=10), with C5holes the outlier
(~588 s) due to PODE obstacle decomposition called per field per evaluation. Coverage stays at
**100%** across all N. Quality (best_fit) and transit behave as expected; the only quality that
degrades with N is ordering optimality (§3.4), which §3.5 addresses.

## 4. Takeaways
1. The joint GA beats matched-budget random search on every non-trivial campaign (+5% to +22%, all
   `p<0.001`), at 100% coverage.
2. Cost is dominated by per-field coverage parameters; **ordering is a secondary lever** whose value
   tracks the transit-to-coverage ratio (shown directly via the truck-speed sweep).
3. **Under a fixed budget, optimizing a weak/homogeneous dimension is net harmful** — it dilutes
   effort on the dominant levers. Dimensions pay off only with both a real lever and field
   heterogeneity (drone selection at scale; direction when orientations differ; ordering when
   transit dominates).
4. On the ordering subproblem the GA is near-exact at small N; **`inversion` is now the default
   order mutation** (was `swap`), and an **NN-seeded hybrid** removes the GA's growing ordering
   deficit at large N for free.
5. Everything is reproducible end-to-end and penalty-free on coverage throughout.

## 5. Reproduce (current pipeline)
```bash
venv39\Scripts\python.exe scripts/exp_campaigns.py          # 9 campaigns + 5-drone fleet
venv39\Scripts\python.exe scripts/exp_campaign_varied.py    # + C5varied (elongated/rotated)
venv39\Scripts\python.exe scripts/exp_ordering.py           # exact optimal / NN / default tours
venv39\Scripts\python.exe scripts/exp_tsp_operators.py      # operators + rk encoding vs exact TSP
venv39\Scripts\python.exe scripts/exp_run.py --ngen 40 --pop 50 --seeds 8 --workers 14 ^
    --nn_seed --transit_roles C5mixed,C10grid --resume      # full 488-job matrix (resumable)
venv39\Scripts\python.exe scripts/exp_analyze.py            # tables + figures
venv39\Scripts\python.exe scripts/exp_figures_maps.py       # campaign gallery + example plan maps
venv39\Scripts\python.exe scripts/make_paper_docx.py        # render the paper draft
```
