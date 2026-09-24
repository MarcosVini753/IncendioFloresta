from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import exportar_perigo_2015 as exporter
from pipeline import dados


class DangerExporterUnitTest(unittest.TestCase):
    def test_calendar_has_every_day_of_2015(self):
        dates = exporter.calendar_2015()
        self.assertEqual(len(dates), 365)
        self.assertEqual(dates[0], "2015-01-01")
        self.assertEqual(dates[-1], "2015-12-31")
        differences = np.diff(np.asarray(dates, dtype="datetime64[D]")).astype(int)
        self.assertTrue((differences == 1).all())

    def test_weighted_aggregation_reproduces_native_means(self):
        native = np.array([0.1, 0.3, 0.8, 1.0])
        groups = np.array([0, 0, 1, 1])
        result = exporter.aggregate(native, groups, np.array([2, 2]))
        np.testing.assert_allclose(result, [0.2, 0.9])

    def test_aggregation_rejects_non_finite_and_out_of_domain(self):
        for values in (np.array([np.nan]), np.array([-0.1]), np.array([1.1])):
            with self.assertRaises(ValueError):
                exporter.aggregate(values, np.array([0]), np.array([1]))

    def test_checkpoint_can_resume_independent_dates(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            exporter, "CHECKPOINTS", Path(directory)
        ):
            Path(directory).mkdir(exist_ok=True)
            values = np.full((365, 212), np.nan)
            completed = np.zeros(365, dtype=bool)
            values[236] = 0.5
            completed[236] = True
            exporter.save_checkpoint("gradboost", values, completed)
            restored_values, restored_completed = exporter.load_checkpoint("gradboost", 365, 212)
            self.assertEqual(int(restored_completed.sum()), 1)
            self.assertTrue(restored_completed[236])
            np.testing.assert_allclose(restored_values[236], 0.5)
            self.assertTrue(np.isnan(restored_values[0]).all())

    def test_fire_context_excludes_the_current_day(self):
        result = dados.contagio(
            np.array([0.0]), np.array([0.0]), np.array([10]),
            np.array([0.0, 0.0]), np.array([0.0, 0.0]), np.array([9, 10]),
        )
        self.assertEqual(result["fogo_5km_3d"][0], 1)
        self.assertEqual(result["dias_desde_fogo_vizinho"][0], 1)

    def test_public_product_when_present(self):
        if not (exporter.PRODUTO / "manifest.json").exists():
            self.skipTest("produto anual ainda em processamento")
        exporter.validate_product()


if __name__ == "__main__":
    unittest.main()
