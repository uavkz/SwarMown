# 3D Enhancement Plan — SwarMown

## Paper Thesis

Extend UAV swarm coverage path planning from 2D to 3D: when a flight segment crosses an obstacle (hole), the planner can choose to **fly around** (existing 2D detour) **or fly over** (climb above the obstacle, cross, descend). The GA optimizes this choice per-obstacle per-segment, jointly with existing genes (direction, start corner, drones, truck stops). A terrain-aware cost model accounts for climb/descent energy, speed, and time.

**Previous publications**: (1) base 2D coverage without obstacles, (2) 2D coverage with obstacle avoidance via polygon decomposition + boundary detour. This paper adds the third dimension.

---

## What Makes It Publishable

1. **Novel decision variable**: per-obstacle over-vs-around is a discrete choice the GA optimizes — no prior CPP swarm work does this (verify in lit review)
2. **Realistic 3D cost model**: climb/descent penalizes energy and time differently from horizontal flight — not just Euclidean 3D distance
3. **Quantifiable trade-off**: small/low obstacles → cheaper to fly over; large/tall obstacles → cheaper to fly around. The crossover point depends on drone parameters, obstacle geometry, and terrain
4. **Backward-compatible**: with all obstacles set to "go around", reproduces the published 2D results exactly

---

## Implementation Plan

### Phase 1 — Obstacle Height Model (small, prerequisite)

**Goal**: give obstacles (holes) a height property so the system knows how high to climb.

- [ ] Add `height` field to hole data in `Field.holes_serialized` (each hole gets a height in meters, default 0)
- [ ] Parse hole heights in `service_routing.py` when loading holes
- [ ] Update web UI (manage_field template) to accept obstacle height input
- [ ] Add CLI arg `--obstacle_heights` (JSON list) to genetic scripts as alternative input

**Scope**: ~50 lines changed. No behavior change yet.

### Phase 2 — 3D Cost Model (core contribution)

**Goal**: distance, time, and energy calculations account for altitude changes.

#### 2a. 3D Distance

Current `calc_vincenty()` returns 2D great-circle distance. Add:

```python
def calc_distance_3d(p1, p2, h1, h2):
    d_horizontal = calc_vincenty(p1, p2) * 1000  # meters
    d_vertical = abs(h2 - h1)  # meters
    return math.sqrt(d_horizontal**2 + d_vertical**2)
```

This is the simplest correct extension. Vincenty handles Earth curvature horizontally; vertical is small enough to be Euclidean.

#### 2b. Flight Altitude Constraints

All drones must fly within `[height_min, height_max]` AGL (meters above ground level):
- `height_min` — working/spray altitude (e.g. 10m). Drone flies at this altitude during normal coverage.
- `height_max` — regulatory ceiling or drone physical limit (e.g. 120m). Fly-over altitude cannot exceed this.
- Implications:
  - If `obstacle_height + safety_margin > height_max` → **must** go around (can't climb high enough)
  - If `obstacle_height + safety_margin < height_min` → no avoidance needed (already above at working altitude)
  - Interesting zone: `height_min < obstacle_height + margin < height_max` — this is where the over-vs-around decision matters
- Passed as CLI args to GA scripts: `--height_min 10 --height_max 120 --safety_margin 5`

#### 2c. Drone Climb/Descent Parameters

Add to `Drone` model:
- `climb_rate` (m/s, default 3.0) — max vertical speed going up
- `descent_rate` (m/s, default 2.0) — max vertical speed going down
- `energy_per_meter_climb` (Wh/m or dimensionless cost multiplier, default 1.5) — energy penalty for gaining altitude vs horizontal flight

**Alternative (simpler)**: skip new model fields, use CLI args in GA scripts. Faster to implement, sufficient for paper. **Recommended for first pass.**

#### 2c. Flight Time with Altitude

Extend `waypoints_flight_time()`:
- For each segment, compute horizontal distance and vertical delta
- Horizontal time = horizontal_dist / horizontal_speed (existing logic with turn slowdown)
- Vertical time = vertical_delta / climb_rate (or descent_rate)
- Segment time = max(horizontal_time, vertical_time) — drone moves both horizontally and vertically simultaneously, limited by the slower axis
- **Alternative**: segment time = horizontal_time + vertical_time (sequential climb then fly) — less realistic but simpler. Could test both.

#### 2d. Flight Cost with Altitude

Extend `drone_flight_price()`:
- Add energy cost for altitude gain: `price_per_meter_climb * total_climb_meters`
- Or fold it into distance by converting climb meters to "equivalent horizontal km"

**Deliverable**: updated `utils.py` with 3D-aware distance, time, cost functions. All existing tests must still pass (when heights are uniform, results identical to 2D).

### Phase 3 — Over-vs-Around Obstacle Avoidance (key novelty)

**Goal**: when a segment crosses an obstacle, evaluate both options and pick the cheaper one — or let the GA decide.

#### Option A — Greedy per-segment decision (simpler, implement first)

In `adjust_path_around_holes()`, for each crossing:

1. **Around cost**: compute detour path (existing `single_segment_adjust`), estimate distance + time
2. **Over cost**: compute fly-over path:
   - Climb from current altitude to `obstacle_height + safety_margin` before the obstacle
   - Cross horizontally at that altitude
   - Descend back to working altitude after the obstacle
   - 3 waypoints: (start → climb_point → over_point → descend_point → end)
3. Pick whichever has lower cost

```python
def avoid_obstacle_3d(start_pt, end_pt, hole, hole_height,
                       current_altitude, safety_margin, drone_params):
    around_path = single_segment_adjust(start_pt, end_pt, hole)
    around_cost = estimate_path_cost(around_path, current_altitude, drone_params)

    over_path = compute_flyover_path(start_pt, end_pt, hole,
                                      hole_height + safety_margin)
    over_cost = estimate_path_cost_3d(over_path, drone_params)

    if over_cost < around_cost:
        return over_path, "over"
    else:
        return around_path, "around"
```

**Pro**: simple, no GA changes needed, already gives 3D benefit.
**Con**: greedy — doesn't consider downstream effects of altitude choice.

#### Option B — GA-optimized obstacle avoidance strategies (stronger for paper)

**Key insight**: a single bit per obstacle is too coarse. The same obstacle may be better to fly over when the flight line crosses its narrow axis (short fly-over, long detour) but better to go around when crossing its wide axis (long fly-over, short detour). The optimal strategy depends on:
- **Crossing geometry** — entry/exit angle, crossing width through the obstacle
- **Obstacle shape** — elongated obstacles have very different narrow-side vs wide-side crossings
- **Sequential context** — if the drone is already high from a previous fly-over, climbing a bit more to clear the next obstacle is cheap; climbing from working altitude is expensive

Typical mission has **tens of crossings** per obstacle (every zamboni row that passes through it creates a gap-crossing, plus row transitions and fly-to/fly-back). Most within-row crossings share the same angle (determined by gene[0] — direction), but row-transition crossings differ.

**Flight altitude constraint**: drones must fly within `[height_min, height_max]` AGL (meters). Typically `height_min` = working/spray altitude (e.g. 10m), `height_max` = regulatory or drone ceiling (e.g. 120m). This constrains fly-over decisions:
- If `obstacle_height + safety_margin > height_max` → **must** go around (can't fly high enough)
- If `obstacle_height + safety_margin < height_min` → obstacle is below working altitude, no avoidance needed at all (already above it)

Below are sub-options for the 5th gene, from simplest to most expressive. All fit the GA framework. Each has a **per-hole** variant (one gene value per obstacle) and a **single** variant (one gene value for the entire flight, shared across all obstacles — ablation study to show per-hole matters).

---

##### B1 — Per-hole binary

```python
individual[4] = [0, 1, 1, 0, ...]  # len = num_holes, 0=around, 1=over
```

- One bit per hole. All crossings of hole_i use the same strategy regardless of geometry.
- If "over": fly at `obstacle_height + safety_margin`, clamped to `[height_min, height_max]`.
- Mutation: flip each bit with `MUTATION_CHANCE`.
- Crossover: two-point on the binary list.
- Search space: `2^H` (tiny).
- **Limitation**: cannot learn "over when crossing narrow side, around when crossing wide side."
- **Use as**: simplest 3D baseline.
- **B1-single**: one bit for entire flight. All obstacles get the same strategy. Pure ablation.

##### B2 — Per-hole max-climb threshold

```python
individual[4] = [12.0, 5.0, 20.0, ...]  # len = num_holes, meters
```

- Each hole gets a **maximum acceptable climb** threshold N (continuous, meters).
- Decision rule **depends on current drone altitude at the moment of crossing**:
  - `gap = obstacle_height + safety_margin - current_altitude`
  - If `gap ≤ 0` → already above obstacle → **always fly over** (free, no climb needed)
  - If `0 < gap ≤ N` → small climb → **fly over** (climb to `obstacle_height + safety_margin`)
  - If `gap > N` → too much climbing → **go around**
- Fly-over altitude = `max(current_altitude, obstacle_height + safety_margin)`, clamped to `height_max`.
- Mutation: Gaussian noise (σ = 10m), clamped to `[0, height_max - height_min]`.
- Crossover: blend or two-point on float list.
- Search space: `H` continuous dimensions.
- **Creates natural altitude persistence**: if a previous fly-over left the drone at 30m, and the next obstacle is 25m tall, gap = 0 → fly over for free. The GA doesn't need a separate persistence rule — it emerges from tracking current altitude through the evaluation.
- **Context-dependent**: same obstacle, same flight direction, but different decisions depending on what happened before. A drone that just climbed over obstacle A stays high and cheaply clears obstacle B; a drone at working altitude might go around B instead.
- **B2-single**: one threshold N for all holes. "I'll climb up to N meters for any obstacle, otherwise go around."

##### B3 — Per-hole crossing-width threshold

```python
individual[4] = [150.0, 80.0, 200.0, ...]  # len = num_holes, threshold in meters
```

- Each hole gets a **crossing-width threshold** (continuous, meters).
- Decision rule: for each individual crossing event, compute the **crossing width** = distance the straight-line segment travels inside the obstacle polygon (`LineString.intersection(hole).length` in projected coords). If `crossing_width < threshold` → fly over; else → go around.
- Fly-over altitude = `obstacle_height + safety_margin`, clamped to `height_max`.
- Mutation: Gaussian noise (σ = 50m), clamped to `[0, max_obstacle_diameter]`.
- Crossover: blend or two-point.
- **Direction-aware at the crossing level**: in the same mission, wide crossings of hole_i go around while narrow crossings fly over — decided dynamically per crossing event.
- **Key advantage**: captures the "narrow side over, wide side around" scenario naturally. The GA evolves the optimal width cutoff per obstacle.
- **Limitation**: uses only one geometric feature (width). Doesn't consider current altitude or climb cost.
- **B3-single**: one threshold for all holes. "Fly over any obstacle if crossing it takes less than T meters, otherwise go around."

##### B4 — Per-hole directional arc

```python
individual[4] = [
    (45.0, 135.0),    # hole 0: fly over if approach angle in [45°, 135°], else around
    (170.0, 350.0),   # hole 1: fly over if approach angle in [170°, 350°]
    ...
]
```

- Each hole gets **two angles** (continuous, 0–360°) defining an arc of approach directions.
- Decision rule: compute the approach angle of the crossing segment (`math.atan2(dy, dx)` in degrees). If angle falls within `[angle_start, angle_end]` (mod 360) → fly over; else → go around.
- If `angle_start == angle_end` → never fly over (degenerate arc). If `angle_end - angle_start ≈ 360` → always fly over.
- Fly-over altitude = `obstacle_height + safety_margin`, clamped to `height_max`.
- Mutation: Gaussian noise (σ = 30°) on each angle, wrapped mod 360.
- Crossover: two-point on the flattened float list.
- Search space: `2*H` continuous dimensions.
- **Directly encodes "fly over from this direction, go around from that direction"**: for an elongated obstacle, the GA learns an arc perpendicular to the long axis (narrow crossings) as the "fly over" zone.
- **Intuitive geometric interpretation**: the arc corresponds to a range of approach directions where fly-over is efficient.
- **B4-single**: one arc for all holes. "When approaching any obstacle from [α, β], fly over; otherwise go around."

##### B5 — Max-climb threshold + crossing-width threshold (combined, recommended)

```python
individual[4] = [
    (12.0, 150.0),    # hole 0: (max_climb_m, width_threshold_m)
    (5.0,  80.0),     # hole 1
    ...
]
```

- Each hole gets **two values**: a max-climb threshold (from B2) AND a crossing-width threshold (from B3).
- Decision rule (both conditions must be met to fly over):
  - `gap = obstacle_height + safety_margin - current_altitude`
  - `crossing_width = line.intersection(hole).length`
  - If `gap ≤ max_climb` AND `crossing_width < width_threshold` → **fly over**
  - Else → **go around**
  - Special case: if `gap ≤ 0` (already above) → **always fly over** regardless of width
- Fly-over altitude = `max(current_altitude, obstacle_height + safety_margin)`, clamped to `height_max`.
- Mutation: independent Gaussian noise on both values.
- Search space: `2*H` continuous dimensions.
- **Combines altitude-awareness (B2) with geometry-awareness (B3)**:
  - Width threshold filters by crossing geometry (narrow → over, wide → around)
  - Max-climb threshold filters by energy cost (cheap climb → over, expensive climb → around)
  - Together: "fly over this obstacle only when the crossing is narrow AND I don't have to climb too much"
- **Altitude persistence is automatic** (from B2): drone stays high after a fly-over, making subsequent fly-overs cheaper (gap ≤ 0 → always over).
- **B5-single**: one `(max_climb, width_threshold)` pair for all holes.

##### B6 — Directional arc + max-climb threshold (alternative combined)

```python
individual[4] = [
    (45.0, 135.0, 12.0),    # hole 0: (arc_start, arc_end, max_climb_m)
    (170.0, 350.0, 8.0),    # hole 1
    ...
]
```

- Each hole gets **three values**: directional arc (from B4) + max-climb threshold (from B2).
- Decision rule:
  - If approach angle is within `[arc_start, arc_end]` AND `gap ≤ max_climb` → **fly over**
  - If `gap ≤ 0` (already above) AND angle in arc → **fly over**
  - Else → **go around**
- Search space: `3*H` continuous dimensions.
- **Combines directional awareness (B4) with altitude awareness (B2)**: "from this direction AND if climb is cheap → fly over."
- **B6-single**: one `(arc_start, arc_end, max_climb)` triple for all holes.

---

##### Altitude persistence — emergent in B2, B5, B6

Unlike the previous plan version, altitude persistence is **not a separate post-processing step**. It emerges naturally from the B2/B5/B6 max-climb threshold:

1. Drone flies over obstacle A at 30m AGL.
2. Next crossing of obstacle B (25m tall). `gap = 25 + 5 - 30 = 0`. Gap ≤ 0 → already above → fly over for free.
3. Drone stays at 30m, clears B without climbing.
4. Eventually no more crossings → drone descends to working altitude.

The GA learns this implicitly: a generous max-climb threshold causes the first fly-over, and subsequent obstacles are cleared for free because the drone is already high. The cost of the initial climb is amortized across multiple obstacle crossings.

For B1/B3/B4 (no altitude tracking), altitude persistence must be added as explicit post-processing: scan consecutive "over" decisions and maintain altitude between them.

---

#### Summary of B sub-options

| Option | Genes per hole | Direction-aware? | Altitude-aware? | Altitude persistence? | Search space |
|---|---|---|---|---|---|
| B1 | 1 bit | No | No | Needs post-proc | `2^H` discrete |
| B2 | 1 float | No | **Yes** (current alt) | **Emergent** | `H` continuous |
| B3 | 1 float | **Yes** (crossing width) | No | Needs post-proc | `H` continuous |
| B4 | 2 floats | **Yes** (approach angle) | No | Needs post-proc | `2*H` continuous |
| B5 | 2 floats | **Yes** (width) + **Yes** (alt) | **Yes** | **Emergent** | `2*H` continuous |
| B6 | 3 floats | **Yes** (angle) + **Yes** (alt) | **Yes** | **Emergent** | `3*H` continuous |

Where H = number of holes.

Each option also has a **-single** ablation variant: one gene value for all holes instead of per-hole. Same decision logic, but shared parameters. Purpose: experimentally show that per-hole optimization matters (or doesn't, for simple scenarios).

#### Recommended approach for the paper:
1. Implement **B1** + **B1-single** as baselines (trivial)
2. Implement **B5** + **B5-single** as the main method (best novelty/complexity ratio — combines geometry + altitude awareness with emergent persistence)
3. Implement **B2** + **B2-single** (altitude-only ablation — shows value of crossing-width awareness)
4. Implement **B3** + **B3-single** (width-only ablation — shows value of altitude awareness)
5. Implement **greedy** (Option A) as a non-GA comparator
6. Compare all against 2D-only baseline
7. Optionally implement **B4** or **B6** if reviewers ask about directional approaches

#### Fly-over waypoint generation

```python
def compute_flyover_path(start_pt, end_pt, hole, fly_over_altitude, current_alt):
    """Generate waypoints to fly over an obstacle."""
    # Find entry/exit points: where the segment intersects hole boundary
    line = LineString([start_pt, end_pt])
    intersection = line.intersection(hole.boundary)
    entry_pt, exit_pt = get_ordered_intersections(intersection, start_pt)

    # Pull back entry/exit by safety margin horizontally
    entry_pt = pull_back(entry_pt, start_pt, margin=10)  # 10m before hole
    exit_pt = pull_back(exit_pt, end_pt, margin=10)       # 10m after hole

    # Generate path: start → climb at entry → fly level over → descend at exit → end
    return [
        (*start_pt, current_alt),
        (*entry_pt, fly_over_altitude),   # climb
        (*exit_pt, fly_over_altitude),    # level over obstacle
        (*end_pt, current_alt),           # descend
    ]
```

### Phase 4 — Terrain-Aware Grid (optional, strengthens paper)

**Goal**: integrate terrain elevation into route planning, not just at export time.

- Move `get_elevations_for_points_dict()` from export-time to grid-generation-time
- Each grid point gets a terrain elevation: `[lon, lat, elevation]`
- Working altitude = `terrain_elevation + AGL_height` (terrain-following)
- Cost model uses actual altitude differences between consecutive waypoints

**Why optional**: can be a separate contribution. The over-vs-around novelty works without terrain data (just use flat terrain assumption + obstacle heights). But terrain data makes the cost model more realistic and the paper stronger.

**Risk**: Open Elevation API is slow/unreliable for many points. Mitigation: use local DEM raster (SRTM 30m) via `rasterio` instead. Or pre-cache all needed elevations.

### Phase 5 — GA Tuning for 3D (if Phase 3B chosen)

- Adjust mutation rates for the new obstacle_strategies gene
- Possibly add a `fly_altitude` continuous gene (target altitude for over-flights) instead of using `obstacle_height + margin`
- Re-tune population size and ngen for expanded search space
- Compare convergence speed: 2D GA vs 3D GA

---

## Experimental Design

### Test Scenarios (missions)

Use existing missions from the DB + create new ones:

| Scenario | Field | Holes | Hole Heights | Purpose |
|---|---|---|---|---|
| S1 | Small rectangle | 1 small, low hole (5m) | 5m | Over should dominate |
| S2 | Small rectangle | 1 small, tall hole (50m) | 50m | Around should dominate |
| S3 | Small rectangle | 1 large, low hole (5m) | 5m | Over should dominate (long detour) |
| S4 | Small rectangle | 1 large, tall hole (50m) | 50m | Trade-off region |
| S5 | Small rectangle | 1 elongated low hole (aspect 5:1) | 10m | B5 should beat B1 — narrow vs wide crossings differ |
| S6 | Small rectangle | 1 elongated tall hole (aspect 5:1) | 40m | Even elongated, tall → around dominates most crossings |
| S7 | Big rectangle | 3 mixed holes (square + elongated) | 5/20/40m | GA must find optimal mix per hole |
| S8 | Big rectangle | 2 close holes in a line | 15/15m | Tests altitude persistence (stay high between them) |
| S9 | Complex polygon | 5+ holes, varied sizes and shapes | 5-50m | Stress test, realistic |
| S10 | Existing fields (Свекла, Соя, Сайран) | Their holes | Varied | Real-world relevance |

### Metrics to Measure

1. **Total cost** (fitness): drone_price + salary + penalty — primary optimization target
2. **Total flight distance** (km): horizontal + vertical components
3. **Total flight time** (hours): bottleneck drone
4. **Number of over-flights vs detours**: how often GA chooses over vs around
5. **Coverage completeness**: should be 100% in all valid solutions
6. **GA convergence**: generations to reach near-optimal, compare 2D vs 3D
7. **Computation time**: wall-clock per generation, overhead of 3D cost model

### Comparisons (paper tables/figures)

| Comparison | What It Shows |
|---|---|
| **2D-only vs Greedy vs B1 vs B5** | Main result: 3D methods reduce cost, B5 best |
| **B5 evolved threshold analysis** | What crossing-width thresholds does the GA converge to? Do they correlate with obstacle shape? |
| **B5 evolved altitude analysis** | What fly-over altitudes does the GA converge to per obstacle? How do they relate to obstacle heights? |
| **Per-crossing decision map** | Visualize which crossings went over vs around — shows the direction-dependence |
| **Vary obstacle height** (fixed size) | Crossover point where over→around |
| **Vary obstacle size** (fixed height) | Crossover point where around→over |
| **Elongated vs square obstacles** | Does B5 (direction-aware) beat B1 (not direction-aware) more on elongated obstacles? |
| **Vary num obstacles** | Scalability of 3D approach |
| **Vary drone climb rate** | Sensitivity to drone parameters |
| **Convergence curves** | GA efficiency: 2D vs B1 vs B5 |
| **Altitude persistence benefit** | With vs without sequential altitude merging — how much does avoiding descent+re-climb save? |

### Figures for Paper

1. **Visualization of 2D detour vs 3D fly-over** — side-by-side map views + altitude profile showing the same obstacle crossed both ways
2. **Per-crossing decision map** — top-down field view, each crossing colored by over (red/up arrow) vs around (blue/curved arrow). Shows that the GA learns direction-dependent strategies for elongated obstacles
3. **Altitude profile along flight path** — X=distance along path, Y=altitude. Shows climb/level/descend for fly-overs, constant altitude for arounds, and altitude persistence between consecutive fly-overs
4. **Cost breakdown bar chart** — 2D vs Greedy vs B1 vs B5: horizontal distance cost, climb energy cost, time cost, detour distance cost
5. **Crossover point heatmap** — obstacle height (Y) vs obstacle crossing-width (X), colored by optimal strategy. Shows the threshold boundary that B5 learns
6. **Evolved threshold vs obstacle geometry scatter** — for each obstacle across all scenarios, plot (obstacle aspect ratio, evolved B5 threshold). Shows correlation
7. **Convergence curves** — fitness over generations for 2D / B1 / B5, showing B5 converges to better solutions
8. **3D path visualization** — oblique/perspective view with altitude changes rendered (matplotlib 3D or Cesium/deck.gl screenshot)
9. **Elongated obstacle case study** — the scenario where B5 clearly outperforms B1 because it flies over the narrow crossings and goes around the wide ones

---

## Implementation Order & Dependencies

```
Phase 1 (obstacle heights)
    ↓
Phase 2 (3D cost model)
    ↓
Phase 3A (greedy over-vs-around)  →  run experiments with greedy
    ↓
Phase 3B (GA-optimized strategies) → run experiments with GA
    ↓                                     ↓
Phase 5 (GA tuning)               compare greedy vs GA
    ↓
Phase 4 (terrain, optional)       → additional experiments if time permits
```

**Minimum viable paper**: Phases 1 + 2 + 3A + experiments with greedy = already publishable.
**Stronger paper**: add Phase 3B (GA optimization of over/around choice).
**Strongest paper**: add Phase 4 (terrain-aware) + Phase 5 (GA tuning).

---

## Estimated Effort

| Phase | Effort | Risk |
|---|---|---|
| Phase 1 | Small (1-2 days) | Low |
| Phase 2 | Medium (3-5 days) | Low — straightforward math |
| Phase 3A | Medium (3-5 days) | Medium — fly-over geometry edge cases |
| Phase 3B | Medium (3-5 days) | Low — GA extension is mechanical |
| Phase 4 | Large (5-7 days) | High — DEM data, API reliability, caching |
| Phase 5 | Small (2-3 days) | Low |
| Experiments | Medium (3-5 days) | Low — scripting + waiting for GA runs |
| Paper writing | Large (2-4 weeks) | — |

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| 3D fly-over is always better (trivial result) | Vary obstacle heights to find non-trivial trade-offs. Include tall obstacles where around wins. |
| 3D fly-over is never better (no contribution) | Unlikely if obstacle heights are realistic (5-50m) and climb cost is non-trivial. Adjust energy model. |
| Expanded GA search space hurts convergence | Phase 3B adds only `2^num_holes` discrete choices — small. If needed, seed initial population with greedy solutions. |
| Terrain API too slow for grid-time elevation | Phase 4 is optional. Use local SRTM raster. Or skip terrain, use flat + obstacle heights. |
| Reviewers ask "why not A*" or continuous altitude optimization | Discuss in related work. Continuous altitude adds complexity beyond scope. A* is for point-to-point, not coverage path planning. |

---

## Related Work to Review

- 3D coverage path planning for UAVs (mostly single-drone, terrain following)
- Energy-aware UAV path planning with altitude optimization
- Obstacle avoidance in CPP: 2D polygon decomposition vs 3D fly-over
- Multi-UAV task allocation with heterogeneous altitude constraints
- Agricultural UAV spraying with terrain awareness

---

## Optional Enhancements (future work / if reviewers ask)

1. **Continuous altitude gene** — instead of binary over/around, GA optimizes a continuous altitude per obstacle. Higher altitude = less detour but more climb energy. More expressive but larger search space.
2. **Wind model** — altitude-dependent wind affects energy consumption differently at different heights.
3. **Variable spray effectiveness** — higher altitude = wider but less precise spray swath. Trade-off between coverage efficiency and spray quality.
4. **Dynamic no-fly zones** — obstacles that move or change height over time (e.g., moving vehicles on roads adjacent to fields).
5. **Multi-altitude coverage** — different parts of the field at different altitudes based on terrain slope and crop type.
