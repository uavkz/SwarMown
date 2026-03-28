# Multi-Field Campaign Experiments

## Overview

Experiments to evaluate multi-field campaign optimization. The GA optimizes field visit order, per-field direction/start/drones/car_stops. Experiments compare ordering operators and ablation modes.

## Test Campaigns

Create via Django admin or programmatically:

| Campaign | Fields | Geometry | Purpose |
|----------|--------|----------|---------|
| 2-close | 2 rectangles ~1km apart | Adjacent | Baseline — transit negligible |
| 2-far | 2 rectangles ~50km apart | Separated | Transit dominates cost |
| 3-line | 3 fields in a line (A—B—C) | Linear | Order A-B-C vs C-B-A matters |
| 3-triangle | 3 fields forming triangle | Equidistant | Any order similar transit |
| 5-mixed | 2 close clusters + 1 far field | Clustered | Tests grouping |
| 5-varied | 5 different shapes + sizes | Mixed | Realistic scenario |
| 10-grid | 10 fields in 2x5 grid | Grid layout | Scaling test |

## Experiment 1: Operator Comparison

**Goal**: Find best crossover x mutation combo for ordering gene.

**Matrix**: 3 crossover x 3 mutation = 9 runs per campaign.

| | swap | insert | inversion |
|---|---|---|---|
| **OX** | ox_swap | ox_insert | ox_inversion |
| **PMX** | pmx_swap | pmx_insert | pmx_inversion |
| **CX** | cx_swap | cx_insert | cx_inversion |

**Parameters**: ngen=25, population=50, mutation_chance=0.1, max_time=12h, borderline=4h

**Metrics**: best fitness, convergence speed (generation where 90% of final fitness reached), diversity (unique orderings in final population)

**Run**: `python scripts/genetic_loop_multi.py` (Phase 1)

**Expected**: OX + swap or OX + inversion likely best (standard TSP result). PMX preserves adjacencies which matters less here since fields aren't sequential.

## Experiment 2: Ablation Study

**Goal**: Which optimization dimensions contribute most to cost reduction?

**Variants** (all using best operators from Exp 1):

| Ablation | What's disabled | Expected impact |
|----------|----------------|-----------------|
| full | Nothing (baseline) | Best |
| fixed_order | No order optimization | Significant if fields far apart |
| single_direction | Same direction all fields | Moderate — different field shapes prefer different angles |
| single_start | Same start corner | Moderate — affects transit entry/exit |
| single_drones | Same drones all fields | Small — unless drone specs vary |

**Run**: `python scripts/genetic_loop_multi.py` (Phase 2)

**Analysis**: Compare best fitness of each ablation vs full. The gap = importance of that dimension.

## Experiment 3: Scaling

**Goal**: How does GA performance scale with number of fields?

**Setup**: Run best operator combo on campaigns with 2, 3, 5, 10 fields.

**Metrics**: Best fitness, wall-clock time per generation, convergence speed.

**Expected**: Time scales linearly with N (one get_route per field). Search space scales as N! for ordering, so convergence may slow significantly at 10 fields.

## Experiment 4: Transit Speed Sensitivity

**Goal**: How much does truck speed affect optimal ordering?

**Setup**: Run 3-line campaign with truck_speed = 20, 40, 60, 80 km/h.

**Expected**: Slower truck → ordering matters more (transit cost dominates). Faster truck → per-field params matter more.

## Running Experiments

```bash
# Single run
python -m scoop -n 8 scripts/genetic_multi.py \
  --campaign_id 1 --ngen 25 --population_size 50 \
  --order_crossover ox --order_mutation swap \
  --filename experiment_name

# Full experiment matrix
python scripts/genetic_loop_multi.py

# With ablation
python -m scoop -n 8 scripts/genetic_multi.py \
  --campaign_id 1 --ngen 25 --population_size 50 \
  --ablation single_direction --filename ablation_test
```

## Output Files

Each run produces:
- `{filename}.xls` — Excel with Info/Drones/Iterations sheets
- `{filename}.json` — Best individual serialized

## Analysis

Compare across experiments:
1. Load all `.xls` files for a campaign
2. Extract `best_fit` from last iteration row
3. Plot convergence curves (best_fit vs generation)
4. Rank operators by final fitness
5. Compute ablation deltas (fitness gap vs baseline)
