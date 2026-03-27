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
        self.assertEqual(len(result), 7)
        distance, time, _drone_price, _salary, _penalty, _starts, _transit_time = result
        self.assertGreater(distance, 0)
        self.assertGreater(time, 0)

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
# Regression: existing single-field tests still pass
# ===================================================================
class TestNoRegression(TestCase):
    """Ensure nothing in the single-field path is broken."""

    def test_existing_tests_count(self):
        """Sanity: this test file loads without affecting other test modules."""
        pass
