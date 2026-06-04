"""Tests for the converter script's route-param resolution (--serialized vs flags)."""

import json
from types import SimpleNamespace

from django.test import TestCase

from mainapp.models import Drone
from scripts.agroscope_kml_to_plan import _coerce_direction, resolve_route_params


class ResolveRouteParamsTests(TestCase):
    def setUp(self):
        self.drone = Drone.objects.create(name="D", model="M", max_distance_no_load=10, weight=1, max_load=1)
        self.other = Drone.objects.create(name="D2", model="M2", max_distance_no_load=20, weight=1, max_load=1)

    def _args(self, serialized=None):
        return SimpleNamespace(serialized=serialized, drone_id=self.drone.id, direction="simple", start="ne")

    def test_defaults_when_no_serialized(self):
        direction, start, drones, car_move = resolve_route_params(self._args())
        self.assertEqual(direction, "simple")
        self.assertEqual(start, "ne")
        self.assertEqual([d.id for d in drones], [self.drone.id])
        self.assertEqual(car_move, "no")

    def test_serialized_overrides_all(self):
        s = json.dumps([90, "sw", [self.other.id], [0.2, 0.5, 0.8]])
        direction, start, drones, car_move = resolve_route_params(self._args(s))
        self.assertEqual(direction, 90)
        self.assertEqual(start, "sw")
        self.assertEqual([d.id for d in drones], [self.other.id])
        self.assertEqual(car_move, [0.2, 0.5, 0.8])

    def test_partial_serialized_falls_back_to_defaults(self):
        # Only direction given; the rest must fall back.
        direction, start, drones, car_move = resolve_route_params(self._args(json.dumps([135])))
        self.assertEqual(direction, 135)
        self.assertEqual(start, "ne")
        self.assertEqual([d.id for d in drones], [self.drone.id])
        self.assertEqual(car_move, "no")

    def test_empty_elements_fall_back(self):
        # Empty drone list / empty car_points must not override.
        s = json.dumps(["simple", "", [], []])
        direction, start, drones, car_move = resolve_route_params(self._args(s))
        self.assertEqual(direction, "simple")
        self.assertEqual(start, "ne")
        self.assertEqual([d.id for d in drones], [self.drone.id])
        self.assertEqual(car_move, "no")


class CoerceDirectionTests(TestCase):
    def test_keywords_pass_through(self):
        self.assertEqual(_coerce_direction("simple"), "simple")
        self.assertEqual(_coerce_direction("vertical"), "vertical")

    def test_numeric_string_becomes_float(self):
        self.assertEqual(_coerce_direction("45"), 45.0)

    def test_number_passes_through(self):
        self.assertEqual(_coerce_direction(90), 90)
