import os

from django.test import TestCase

from mainapp.models import Drone
from mainapp.utils_excel import log_excel


class LogExcelTests(TestCase):
    """Tests for log_excel() in utils_excel."""

    def setUp(self):
        self.drone = Drone.objects.create(
            name="D1",
            model="M1",
            max_distance_no_load=10,
            weight=5,
            max_load=2,
        )
        self.iterations = [
            {
                "best_distance": 1000,
                "average_distance": 1500,
                "best_time": 1.0,
                "average_time": 2.0,
                "best_drone_price": 5.0,
                "average_drone_price": 8.0,
                "best_salary": 10.0,
                "average_salary": 15.0,
                "best_penalty": 0,
                "average_penalty": 100,
                "best_number_of_starts": 2,
                "average_number_of_starts": 3,
                "best_fit": -15.0,
                "average_fit": -23.0,
                "best_ind": [45.0, "ne", [0], [0.5]],
            }
        ]
        self.info = {
            "population_size": 30,
            "target_weights": (-1.0,),
            "number_of_iterations": 1,
            "mission": "1 - Test",
            "field": "1 - TestField",
            "grid_step": 100,
            "start_price": 3,
            "hourly_price": 10,
            "max_working_speed": 7,
            "borderline_time": 2,
            "max_time": 8,
        }
        self.output_name = "test_log_excel_output"
        self.output_file = f"{self.output_name}.xls"

    def tearDown(self):
        # 3. Cleanup - delete the file if it exists
        if os.path.exists(self.output_file):
            os.remove(self.output_file)

    # 1. Smoke test
    def test_smoke_creates_file(self):
        """Calling log_excel with minimal data creates a file without errors."""
        log_excel(
            name=self.output_name,
            info=self.info,
            drones=[self.drone],
            iterations=self.iterations,
        )
        self.assertTrue(os.path.exists(self.output_file))

    # 2. File exists on disk
    def test_file_exists_on_disk(self):
        """Output .xls file exists on disk after calling log_excel."""
        log_excel(
            name=self.output_name,
            info=self.info,
            drones=[self.drone],
            iterations=self.iterations,
        )
        self.assertTrue(os.path.isfile(self.output_file))
        file_size = os.path.getsize(self.output_file)
        self.assertGreater(file_size, 0, "Output file should not be empty")
