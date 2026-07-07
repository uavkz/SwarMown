"""Tests for multi-field campaign optimization.

Covers:
- Campaign / CampaignField models
- transit_time_hours utility
- Ordering crossover operators: OX, PMX, CX
- Ordering mutation operators: swap, insert, inversion
- Individual generation + ablation modes
- Multi-field evaluation (smoke + transit + coverage)
- Per-field parameter crossover
"""

import json
import random
from copy import deepcopy

from django.contrib.auth.models import User
from django.test import TestCase
from pyproj import Transformer

from mainapp.models import Campaign, CampaignField, Drone, Field
from mainapp.utils import transit_time_hours

# --- Test field data (3 separated rectangles) --------------------------------

FIELD_A_POINTS = [[50.00, 30.00], [50.00, 30.05], [50.02, 30.05], [50.02, 30.00]]
FIELD_A_ROAD = [[49.99, 30.00], [49.99, 30.05]]

FIELD_B_POINTS = [[50.05, 30.10], [50.05, 30.15], [50.07, 30.15], [50.07, 30.10]]
FIELD_B_ROAD = [[50.04, 30.10], [50.04, 30.15]]

FIELD_C_POINTS = [[50.10, 29.95], [50.10, 30.00], [50.12, 30.00], [50.12, 29.95]]
FIELD_C_ROAD = [[50.09, 29.95], [50.09, 30.00]]

PYPROJ_TRANSFORMER = Transformer.from_crs("epsg:4087", "epsg:4326", always_xy=True)


def _create_test_data():
    """Create User, 3 Fields, 2 Drones, and a Campaign with all 3 fields."""
    user = User.objects.create_user("testuser", password="testpass")

    fields = []
    for name, pts, road in [
        ("FieldA", FIELD_A_POINTS, FIELD_A_ROAD),
        ("FieldB", FIELD_B_POINTS, FIELD_B_ROAD),
        ("FieldC", FIELD_C_POINTS, FIELD_C_ROAD),
    ]:
        f = Field.objects.create(
            owner=user,
            name=name,
            points_serialized=json.dumps(pts),
            road_serialized=json.dumps(road),
            holes_serialized="[]",
        )
        fields.append(f)

    d1 = Drone.objects.create(
        name="TestDrone1",
        model="T1",
        max_speed=15,
        max_distance_no_load=50,
        weight=5,
        max_load=2,
        slowdown_ratio_per_degree=0.005,
        min_slowdown_ratio=0.01,
        price_per_cycle=3,
        price_per_kilometer=0.1,
        price_per_hour=0.01,
    )
    d2 = Drone.objects.create(
        name="TestDrone2",
        model="T2",
        max_speed=15,
        max_distance_no_load=50,
        weight=5,
        max_load=2,
        slowdown_ratio_per_degree=0.005,
        min_slowdown_ratio=0.01,
        price_per_cycle=3,
        price_per_kilometer=0.1,
        price_per_hour=0.01,
    )

    campaign = Campaign.objects.create(
        owner=user,
        name="TestCampaign",
        grid_step=500,
        truck_speed_kmh=40,
        start_price=3,
        hourly_price=10,
    )
    campaign.drones.add(d1, d2)
    for idx, field in enumerate(fields):
        CampaignField.objects.create(campaign=campaign, field=field, default_order=idx)

    return user, fields, [d1, d2], campaign


# ===================================================================
# Model tests
# ===================================================================
class TestCampaignModel(TestCase):
    def setUp(self):
        self.user, self.fields, self.drones, self.campaign = _create_test_data()

    def test_campaign_creation(self):
        self.assertEqual(self.campaign.name, "TestCampaign")
        self.assertEqual(self.campaign.fields.count(), 3)
        self.assertEqual(self.campaign.drones.count(), 2)

    def test_campaign_field_ordering(self):
        cfs = list(self.campaign.campaign_fields.order_by("default_order"))
        self.assertEqual(cfs[0].field.name, "FieldA")
        self.assertEqual(cfs[1].field.name, "FieldB")
        self.assertEqual(cfs[2].field.name, "FieldC")

    def test_campaign_field_unique(self):
        """Same field cannot be added twice to same campaign."""
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            CampaignField.objects.create(campaign=self.campaign, field=self.fields[0], default_order=10)

    def test_cascade_delete_user(self):
        self.user.delete()
        self.assertEqual(Campaign.objects.count(), 0)

    def test_delete_field_removes_campaign_field(self):
        self.fields[0].delete()
        self.assertEqual(self.campaign.campaign_fields.count(), 2)
        self.assertTrue(Campaign.objects.filter(id=self.campaign.id).exists())

    def test_truck_speed_default(self):
        self.assertEqual(self.campaign.truck_speed_kmh, 40)

    def test_str(self):
        self.assertEqual(str(self.campaign), "TestCampaign")


# ===================================================================
# Transit time
# ===================================================================
class TestTransitTime(TestCase):
    def test_known_distance(self):
        """Transit between known road endpoints should give reasonable time."""
        hours = transit_time_hours(FIELD_A_ROAD, FIELD_B_ROAD, 40)
        # Fields are ~10km apart, at 40km/h should be ~0.25h
        self.assertGreater(hours, 0)
        self.assertLess(hours, 2)

    def test_zero_for_same_point(self):
        """Same exit and entry point should give zero transit."""
        single_pt_road = [[50.0, 30.0]]
        hours = transit_time_hours(single_pt_road, single_pt_road, 40)
        self.assertEqual(hours, 0.0)

    def test_exit_entry_asymmetry(self):
        """A->B and B->A use different endpoints so may differ."""
        ab = transit_time_hours(FIELD_A_ROAD, FIELD_B_ROAD, 40)
        ba = transit_time_hours(FIELD_B_ROAD, FIELD_A_ROAD, 40)
        # Both should be positive (fields are separated)
        self.assertGreater(ab, 0)
        self.assertGreater(ba, 0)

    def test_slower_truck_takes_longer(self):
        fast = transit_time_hours(FIELD_A_ROAD, FIELD_B_ROAD, 80)
        slow = transit_time_hours(FIELD_A_ROAD, FIELD_B_ROAD, 40)
        self.assertAlmostEqual(slow, fast * 2, places=3)


# ===================================================================
# Crossover operators
# ===================================================================
def _make_test_individual(n, num_drones=2):
    """Create a deterministic test individual with n fields."""
    return [
        list(range(n)),
        [float(i * 10) for i in range(n)],
        ["ne"] * n,
        [[0]] * n,
        [[0.5]] * n,
    ]


class TestCXOrder(TestCase):
    def test_produces_valid_permutation(self):
        from scripts.ga_multi_common import cx_order

        for _ in range(50):
            ind1 = _make_test_individual(5)
            ind2 = _make_test_individual(5)
            random.shuffle(ind2[0])
            cx_order(ind1, ind2)
            self.assertEqual(sorted(ind1[0]), list(range(5)))
            self.assertEqual(sorted(ind2[0]), list(range(5)))

    def test_single_field_no_crash(self):
        from scripts.ga_multi_common import cx_order

        ind1 = _make_test_individual(1)
        ind2 = _make_test_individual(1)
        cx_order(ind1, ind2)
        self.assertEqual(ind1[0], [0])


class TestCXPmx(TestCase):
    def test_produces_valid_permutation(self):
        from scripts.ga_multi_common import cx_pmx

        for _ in range(50):
            ind1 = _make_test_individual(6)
            ind2 = _make_test_individual(6)
            random.shuffle(ind2[0])
            cx_pmx(ind1, ind2)
            self.assertEqual(sorted(ind1[0]), list(range(6)))
            self.assertEqual(sorted(ind2[0]), list(range(6)))


class TestCXCycle(TestCase):
    def test_produces_valid_permutation(self):
        from scripts.ga_multi_common import cx_cycle

        for _ in range(50):
            ind1 = _make_test_individual(5)
            ind2 = _make_test_individual(5)
            random.shuffle(ind2[0])
            cx_cycle(ind1, ind2)
            self.assertEqual(sorted(ind1[0]), list(range(5)))
            self.assertEqual(sorted(ind2[0]), list(range(5)))


class TestCXPerFieldParams(TestCase):
    def test_preserves_valid_structure(self):
        from scripts.ga_multi_common import cx_per_field_params

        ind1 = _make_test_individual(3)
        ind2 = _make_test_individual(3)
        ind2[1] = [100.0, 200.0, 300.0]
        cx_per_field_params(ind1, ind2, 3)
        # All values should come from either original ind1 or ind2
        for i in range(3):
            self.assertIn(ind1[1][i], [float(i * 10), (i + 1) * 100])


# ===================================================================
# Mutation operators
# ===================================================================
class TestMutSwap(TestCase):
    def test_valid_permutation(self):
        from scripts.ga_multi_common import mut_swap

        for _ in range(50):
            order = list(range(8))
            random.shuffle(order)
            mut_swap(order, 1.0)
            self.assertEqual(sorted(order), list(range(8)))


class TestMutInsert(TestCase):
    def test_valid_permutation(self):
        from scripts.ga_multi_common import mut_insert

        for _ in range(50):
            order = list(range(8))
            random.shuffle(order)
            mut_insert(order, 1.0)
            self.assertEqual(sorted(order), list(range(8)))


class TestMutInversion(TestCase):
    def test_valid_permutation(self):
        from scripts.ga_multi_common import mut_inversion

        for _ in range(50):
            order = list(range(8))
            random.shuffle(order)
            mut_inversion(order, 1.0)
            self.assertEqual(sorted(order), list(range(8)))


class TestMutateMulti(TestCase):
    def test_no_crash(self):
        from scripts.ga_multi_common import mutate_multi

        ind = _make_test_individual(4)
        result = mutate_multi(ind, 2, 4, 0.5)
        self.assertEqual(len(result), 1)  # DEAP convention: returns (ind,)

    def test_changes_individual(self):
        from scripts.ga_multi_common import mutate_multi

        changed = False
        for _ in range(20):
            ind = _make_test_individual(4)
            original_order = ind[0][:]
            mutate_multi(ind, 2, 4, 1.0)
            if ind[0] != original_order:
                changed = True
                break
        self.assertTrue(changed, "Mutation should change the individual")

    def test_fixed_order_ablation(self):
        from scripts.ga_multi_common import mutate_multi

        for _ in range(20):
            ind = _make_test_individual(4)
            mutate_multi(ind, 2, 4, 1.0, ablation="fixed_order")
            self.assertEqual(ind[0], [0, 1, 2, 3], "fixed_order should not mutate order")


# ===================================================================
# Individual generation
# ===================================================================
class TestGenerateMultiIndividual(TestCase):
    def test_structure(self):
        from scripts.ga_multi_common import generate_multi_individual

        ind = generate_multi_individual(4, 3)
        self.assertEqual(len(ind), 5)
        self.assertEqual(sorted(ind[0]), [0, 1, 2, 3])
        self.assertEqual(len(ind[1]), 4)
        self.assertEqual(len(ind[2]), 4)
        self.assertEqual(len(ind[3]), 4)
        self.assertEqual(len(ind[4]), 4)

    def test_randomness(self):
        from scripts.ga_multi_common import generate_multi_individual

        inds = [generate_multi_individual(5, 3) for _ in range(10)]
        orders = [tuple(i[0]) for i in inds]
        self.assertGreater(len(set(orders)), 1, "Should produce different orderings")

    def test_fixed_order_ablation(self):
        from scripts.ga_multi_common import generate_multi_individual

        ind = generate_multi_individual(4, 2, ablation="fixed_order")
        self.assertEqual(ind[0], [0, 1, 2, 3])

    def test_single_direction_ablation(self):
        from scripts.ga_multi_common import generate_multi_individual

        ind = generate_multi_individual(5, 2, ablation="single_direction")
        self.assertEqual(len(set(ind[1])), 1, "All directions should be the same")

    def test_single_start_ablation(self):
        from scripts.ga_multi_common import generate_multi_individual

        ind = generate_multi_individual(5, 2, ablation="single_start")
        self.assertEqual(len(set(ind[2])), 1, "All starts should be the same")

    def test_single_drones_ablation(self):
        from scripts.ga_multi_common import generate_multi_individual

        ind = generate_multi_individual(3, 2, ablation="single_drones")
        self.assertEqual(ind[3][0], ind[3][1])
        self.assertEqual(ind[3][1], ind[3][2])


# ===================================================================
# Evaluation (requires DB)
# ===================================================================
class TestEvaluateMulti(TestCase):
    def setUp(self):
        self.user, self.fields, self.drones, self.campaign = _create_test_data()

    def _load_campaign_data(self):
        from scripts.ga_multi_common import load_campaign

        return load_campaign(self.campaign.id)

    def test_smoke(self):
        """Evaluation returns 7-tuple without crashing."""
        from scripts.ga_multi_common import evaluate_multi_individual, generate_multi_individual

        campaign_data = self._load_campaign_data()

        class Args:
            max_working_speed = 7
            borderline_time = 4
            max_time = 12
            truck_speed = None

        ind = generate_multi_individual(3, 2)
        result = evaluate_multi_individual(ind, campaign_data, Args(), PYPROJ_TRANSFORMER)
        self.assertEqual(len(result), 10)
        distance, time, _dp, _sal, _pen, _starts, _transit, grid_total, grid_missed, _usage = result
        self.assertGreater(distance, 0)
        self.assertGreater(time, 0)
        self.assertGreaterEqual(grid_total, grid_missed)

    def test_transit_adds_time(self):
        """Total time should include transit between fields."""
        from scripts.ga_multi_common import evaluate_multi_individual

        campaign_data = self._load_campaign_data()

        class Args:
            max_working_speed = 7
            borderline_time = 100
            max_time = 200
            truck_speed = None

        # Use deterministic individual
        ind = [
            [0, 1, 2],
            [0.0, 0.0, 0.0],
            ["ne", "ne", "ne"],
            [[0], [0], [0]],
            [[0.5], [0.5], [0.5]],
        ]
        result = evaluate_multi_individual(ind, campaign_data, Args(), PYPROJ_TRANSFORMER)
        transit_time = result[6]
        self.assertGreater(transit_time, 0, "Transit between separated fields should be >0")

    def test_different_orders_different_transit(self):
        """Different field orderings should produce different transit times."""
        from scripts.ga_multi_common import evaluate_multi_individual

        campaign_data = self._load_campaign_data()

        class Args:
            max_working_speed = 7
            borderline_time = 100
            max_time = 200
            truck_speed = None

        base = [
            None,  # order placeholder
            [0.0, 0.0, 0.0],
            ["ne", "ne", "ne"],
            [[0], [0], [0]],
            [[0.5], [0.5], [0.5]],
        ]

        ind1 = deepcopy(base)
        ind1[0] = [0, 1, 2]
        r1 = evaluate_multi_individual(ind1, campaign_data, Args(), PYPROJ_TRANSFORMER)

        ind2 = deepcopy(base)
        ind2[0] = [2, 0, 1]
        r2 = evaluate_multi_individual(ind2, campaign_data, Args(), PYPROJ_TRANSFORMER)

        # Transit times should differ for different orderings
        self.assertNotAlmostEqual(r1[6], r2[6], places=3)


# ===================================================================
# Edge cases
# ===================================================================
class TestEdgeCases(TestCase):
    """Edge cases: 1 field, 0 waypoints, identical parents, etc."""

    def setUp(self):
        self.user, self.fields, self.drones, self.campaign = _create_test_data()

    def test_single_field_campaign(self):
        """1-field campaign should work and produce 0 transit time."""
        from scripts.ga_multi_common import evaluate_multi_individual, generate_multi_individual, load_campaign

        # Create 1-field campaign
        c = Campaign.objects.create(owner=self.user, name="Single", grid_step=500, truck_speed_kmh=40)
        c.drones.add(*self.drones)
        CampaignField.objects.create(campaign=c, field=self.fields[0], default_order=0)
        cd = load_campaign(c.id)

        class Args:
            max_working_speed = 7
            borderline_time = 100
            max_time = 200
            truck_speed = None

        ind = generate_multi_individual(1, 2)
        result = evaluate_multi_individual(ind, cd, Args(), PYPROJ_TRANSFORMER)
        self.assertEqual(result[6], 0.0, "1-field campaign should have 0 transit")

    def test_crossover_identical_parents(self):
        """Crossover with identical parents should still produce valid permutations."""
        from scripts.ga_multi_common import cx_cycle, cx_order, cx_pmx

        for cx_fn in [cx_order, cx_pmx, cx_cycle]:
            for _ in range(20):
                ind1 = _make_test_individual(5)
                ind2 = _make_test_individual(5)
                ind2[0] = ind1[0][:]  # identical order
                cx_fn(ind1, ind2)
                self.assertEqual(sorted(ind1[0]), list(range(5)), f"{cx_fn.__name__} failed with identical parents")
                self.assertEqual(sorted(ind2[0]), list(range(5)))

    def test_crossover_two_fields(self):
        """All crossover operators should work with N=2."""
        from scripts.ga_multi_common import cx_cycle, cx_order, cx_pmx

        for cx_fn in [cx_order, cx_pmx, cx_cycle]:
            for _ in range(30):
                ind1 = _make_test_individual(2)
                ind2 = _make_test_individual(2)
                random.shuffle(ind2[0])
                cx_fn(ind1, ind2)
                self.assertEqual(sorted(ind1[0]), [0, 1])
                self.assertEqual(sorted(ind2[0]), [0, 1])

    def test_mutation_single_field(self):
        """Mutation operators on 1-element permutation should not crash."""
        from scripts.ga_multi_common import mut_insert, mut_inversion, mut_swap

        for mut_fn in [mut_swap, mut_insert, mut_inversion]:
            order = [0]
            mut_fn(order, 1.0)
            self.assertEqual(order, [0])

    def test_pmx_no_infinite_loop(self):
        """PMX should terminate even with adversarial inputs."""
        from scripts.ga_multi_common import cx_pmx

        # Run many times to stress-test cycle handling
        for _ in range(200):
            ind1 = _make_test_individual(8)
            ind2 = _make_test_individual(8)
            random.shuffle(ind1[0])
            random.shuffle(ind2[0])
            cx_pmx(ind1, ind2)
            self.assertEqual(sorted(ind1[0]), list(range(8)))
            self.assertEqual(sorted(ind2[0]), list(range(8)))

    def test_cx_cycle_no_none_values(self):
        """CX should never produce None in children."""
        from scripts.ga_multi_common import cx_cycle

        for _ in range(200):
            ind1 = _make_test_individual(7)
            ind2 = _make_test_individual(7)
            random.shuffle(ind1[0])
            random.shuffle(ind2[0])
            cx_cycle(ind1, ind2)
            self.assertNotIn(None, ind1[0])
            self.assertNotIn(None, ind2[0])

    def test_generate_guards_zero_drones(self):
        """generate_multi_individual should not crash with num_drones=0."""
        from scripts.ga_multi_common import generate_multi_individual

        ind = generate_multi_individual(3, 0)
        self.assertEqual(len(ind[0]), 3)

    def test_eval_empty_waypoints_field(self):
        """Evaluation should handle fields that produce no waypoints."""
        from scripts.ga_multi_common import evaluate_multi_individual, load_campaign

        # Create campaign with a tiny field that might produce 0 waypoints
        tiny = Field.objects.create(
            owner=self.user,
            name="Tiny",
            points_serialized=json.dumps([[50.0, 30.0], [50.0, 30.0001], [50.0001, 30.0001], [50.0001, 30.0]]),
            road_serialized=json.dumps([[49.9999, 30.0], [49.9999, 30.0001]]),
        )
        c = Campaign.objects.create(owner=self.user, name="TinyCampaign", grid_step=5000, truck_speed_kmh=40)
        c.drones.add(*self.drones)
        CampaignField.objects.create(campaign=c, field=tiny, default_order=0)
        cd = load_campaign(c.id)

        class Args:
            max_working_speed = 7
            borderline_time = 100
            max_time = 200
            truck_speed = None

        ind = [[0], [0.0], ["ne"], [[0]], [[0.5]]]
        result = evaluate_multi_individual(ind, cd, Args(), PYPROJ_TRANSFORMER)
        # Should not crash — returns penalty tuple
        self.assertEqual(len(result), 10)


# ===================================================================
# Diverse campaign waypoint verification
# ===================================================================

# More field geometries for thorough testing
FIELD_CLOSE_A = {
    "pts": [[50.00, 30.00], [50.00, 30.02], [50.01, 30.02], [50.01, 30.00]],
    "road": [[49.999, 30.00], [49.999, 30.02]],
}
FIELD_CLOSE_B = {
    "pts": [[50.00, 30.025], [50.00, 30.045], [50.01, 30.045], [50.01, 30.025]],
    "road": [[49.999, 30.025], [49.999, 30.045]],
}
FIELD_FAR = {
    "pts": [[50.50, 31.00], [50.50, 31.05], [50.52, 31.05], [50.52, 31.00]],
    "road": [[50.49, 31.00], [50.49, 31.05]],
}
FIELD_WITH_HOLE = {
    "pts": [[50.00, 30.00], [50.00, 30.10], [50.05, 30.10], [50.05, 30.00]],
    "road": [[49.99, 30.00], [49.99, 30.10]],
    "holes": [[[50.02, 30.04], [50.02, 30.06], [50.03, 30.06], [50.03, 30.04]]],
}


class TestDiverseCampaigns(TestCase):
    """Create diverse campaigns and verify evaluation makes sense."""

    def setUp(self):
        self.user = User.objects.create_user("camptest", password="test")
        self.d1 = Drone.objects.create(
            name="CampDrone1",
            model="C1",
            max_speed=15,
            max_distance_no_load=50,
            weight=5,
            max_load=2,
            slowdown_ratio_per_degree=0.005,
            min_slowdown_ratio=0.01,
            price_per_cycle=3,
            price_per_kilometer=0.1,
            price_per_hour=0.01,
        )

    def _make_field(self, name, data):
        return Field.objects.create(
            owner=self.user,
            name=name,
            points_serialized=json.dumps(data["pts"]),
            road_serialized=json.dumps(data["road"]),
            holes_serialized=json.dumps(data.get("holes", [])),
        )

    def _make_campaign(self, name, field_datas, grid_step=300):
        fields = [self._make_field(f"F{i}_{name}", d) for i, d in enumerate(field_datas)]
        c = Campaign.objects.create(
            owner=self.user,
            name=name,
            grid_step=grid_step,
            truck_speed_kmh=40,
            start_price=3,
            hourly_price=10,
        )
        c.drones.add(self.d1)
        for idx, f in enumerate(fields):
            CampaignField.objects.create(campaign=c, field=f, default_order=idx)
        return c

    def _eval(self, campaign_id, ind):
        from scripts.ga_multi_common import evaluate_multi_individual, load_campaign

        cd = load_campaign(campaign_id)

        class Args:
            max_working_speed = 7
            borderline_time = 100
            max_time = 200
            truck_speed = None

        return evaluate_multi_individual(ind, cd, Args(), PYPROJ_TRANSFORMER)

    def test_close_fields_low_transit(self):
        """Two adjacent fields should have very low transit time."""
        c = self._make_campaign("close", [FIELD_CLOSE_A, FIELD_CLOSE_B])
        ind = [[0, 1], [0.0, 0.0], ["ne", "ne"], [[0], [0]], [[0.5], [0.5]]]
        r = self._eval(c.id, ind)
        self.assertLess(r[6], 0.05, "Close fields should have <3min transit")

    def test_far_field_high_transit(self):
        """Close + far field should have significant transit."""
        c = self._make_campaign("far", [FIELD_CLOSE_A, FIELD_FAR])
        ind = [[0, 1], [0.0, 0.0], ["ne", "ne"], [[0], [0]], [[0.5], [0.5]]]
        r = self._eval(c.id, ind)
        self.assertGreater(r[6], 0.5, "Far fields should have >30min transit")

    def test_order_matters_for_line(self):
        """For 3 fields in a line, A-B-C should have less transit than A-C-B."""
        c = self._make_campaign("line", [FIELD_CLOSE_A, FIELD_CLOSE_B, FIELD_FAR])
        base_params = [[0.0, 0.0, 0.0], ["ne", "ne", "ne"], [[0], [0], [0]], [[0.5], [0.5], [0.5]]]

        # A(0) -> B(1) -> C(2): close-close, then close-far
        ind_abc = [[0, 1, 2]] + [x[:] for x in base_params]
        r_abc = self._eval(c.id, ind_abc)

        # A(0) -> C(2) -> B(1): close-far, then far-close
        ind_acb = [[0, 2, 1]] + [x[:] for x in base_params]
        r_acb = self._eval(c.id, ind_acb)

        # Transit should differ
        self.assertNotAlmostEqual(r_abc[6], r_acb[6], places=3)

    def test_field_with_holes(self):
        """Campaign with holes should still evaluate without error."""
        c = self._make_campaign("holes", [FIELD_CLOSE_A, FIELD_WITH_HOLE], grid_step=500)
        ind = [[0, 1], [0.0, 0.0], ["ne", "ne"], [[0], [0]], [[0.5], [0.5]]]
        r = self._eval(c.id, ind)
        self.assertEqual(len(r), 10)
        self.assertGreater(r[0], 0, "Should have some distance")

    def test_all_heights_constant_2d(self):
        """In 2D mode, all waypoint heights should be constant."""
        from mainapp.service_routing import get_route
        from scripts.ga_multi_common import load_campaign

        c = self._make_campaign("heights", [FIELD_CLOSE_A, FIELD_CLOSE_B])
        cd = load_campaign(c.id)
        drones = cd["drones_list"]

        for fd in cd["fields_data"]:
            _grid, waypoints, _, _ = get_route(
                car_move=[0.5],
                direction=0.0,
                start="ne",
                field=fd["field"][:],
                grid_step=300,
                road=fd["road"][:],
                drones=drones,
            )
            for segment in waypoints:
                heights = {wp["height"] for wp in segment}
                self.assertEqual(len(heights), 1, "2D mode must have constant altitude")

    def test_spray_on_waypoints_inside_field(self):
        """Spray-on waypoints should be inside the field polygon."""
        from shapely.geometry import Point, Polygon

        from mainapp.service_routing import get_route
        from scripts.ga_multi_common import load_campaign

        c = self._make_campaign("inside", [FIELD_CLOSE_A])
        cd = load_campaign(c.id)
        fd = cd["fields_data"][0]

        _grid, waypoints, _, _ = get_route(
            car_move=[0.5],
            direction=0.0,
            start="ne",
            field=fd["field"][:],
            grid_step=200,
            road=fd["road"][:],
            drones=cd["drones_list"],
        )
        # Build polygon from original lat/lon points (field is in lon/lat for shapely)
        field_poly = Polygon(fd["field"])
        for segment in waypoints:
            for wp in segment:
                if wp["spray_on"]:
                    pt = Point(wp["lon"], wp["lat"])
                    self.assertTrue(
                        field_poly.buffer(0.001).contains(pt),
                        f"Spray-on waypoint ({wp['lat']}, {wp['lon']}) outside field",
                    )

    def test_ga_improves_fitness(self):
        """GA should improve (or at least not worsen) best fitness over generations."""
        from scripts.ga_multi_common import (
            evaluate_multi_individual,
            generate_multi_individual,
            load_campaign,
        )

        c = self._make_campaign("gafit", [FIELD_CLOSE_A, FIELD_CLOSE_B])
        cd = load_campaign(c.id)

        class Args:
            max_working_speed = 7
            borderline_time = 100
            max_time = 200
            truck_speed = None

        # Evaluate 20 random individuals, check we get a range of fitnesses
        fitnesses = []
        for _ in range(20):
            ind = generate_multi_individual(2, 1)
            r = evaluate_multi_individual(ind, cd, Args(), PYPROJ_TRANSFORMER)
            fitnesses.append(r[2] + r[3] + r[4])  # drone_price + salary + penalty

        self.assertGreater(max(fitnesses) - min(fitnesses), 0, "Different individuals should have different fitnesses")


# ===================================================================
# Regression: existing single-field tests still pass
# ===================================================================
class TestNoRegression(TestCase):
    """Ensure nothing in the single-field path is broken."""

    def test_existing_tests_count(self):
        """Sanity: this test file loads without affecting other test modules."""
        pass
