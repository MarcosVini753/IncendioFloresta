from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import exportar_perigo_2015 as exporter
from pipeline import dados


class DangerExporterUnitTest(unittest.TestCase):
    @staticmethod
    def _checkpoint_contract():
        features = [{"properties": {"id": "AC-R00C00"}}]
        return exporter.build_checkpoint_contract(
            [f"predictor_{index}" for index in range(44)], features, 196_455
        )

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

    def test_checkpoint_contract_is_created_and_reused(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            exporter, "CHECKPOINTS", Path(directory)
        ):
            contract = self._checkpoint_contract()
            exporter.ensure_checkpoint_contract(contract)
            exporter.ensure_checkpoint_contract(contract)
            self.assertTrue((Path(directory) / exporter.CHECKPOINT_MANIFEST).exists())

    def test_checkpoint_contract_rejects_mismatch(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            exporter, "CHECKPOINTS", Path(directory)
        ):
            contract = self._checkpoint_contract()
            exporter.ensure_checkpoint_contract(contract)
            incompatible = dict(contract, training_rows=1)
            with self.assertRaisesRegex(ValueError, "diverge"):
                exporter.ensure_checkpoint_contract(incompatible)

    def test_checkpoint_contract_rejects_legacy_artifacts(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            exporter, "CHECKPOINTS", Path(directory)
        ):
            legacy = Path(directory) / "fuzzy_knn_k29"
            legacy.mkdir()
            np.save(legacy / "000.npy", np.zeros(212))
            with self.assertRaisesRegex(ValueError, "sem manifesto"):
                exporter.ensure_checkpoint_contract(self._checkpoint_contract())

    def test_fire_context_excludes_the_current_day(self):
        result = dados.contagio(
            np.array([0.0]), np.array([0.0]), np.array([10]),
            np.array([0.0, 0.0]), np.array([0.0, 0.0]), np.array([9, 10]),
        )
        self.assertEqual(result["fogo_5km_3d"][0], 1)
        self.assertEqual(result["dias_desde_fogo_vizinho"][0], 1)

    def test_complete_checkpoints_generate_the_public_product(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoints = root / "checkpoints"
            checkpoints.mkdir()
            product = root / "produtos" / "perigo" / "v1" / "2015"
            features = [{
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[
                    [-70.0, -9.0], [-69.9, -9.0], [-69.9, -8.9],
                    [-70.0, -8.9], [-70.0, -9.0],
                ]]},
                "properties": {
                    "id": f"AC-R00C{index:02d}",
                    "centroid": [-69.95, -8.95],
                    "n_source_cells": 307_199 if index == 0 else 1,
                    "aggregation": "mean",
                },
            } for index in range(212)]
            predictors = [f"predictor_{index}" for index in range(44)]
            contract = exporter.build_checkpoint_contract(predictors, features, 196_455)
            values = np.full((365, 212), 0.5)
            completed = np.ones(365, dtype=bool)
            for spec in exporter.MODEL_SPECS:
                np.savez_compressed(
                    checkpoints / f"scores_{spec['id']}.npz",
                    values=values,
                    completed=completed,
                )
            with patch.object(exporter, "CHECKPOINTS", checkpoints), patch.object(
                exporter, "PRODUTO", product
            ):
                exporter.export_product(
                    features, exporter.calendar_2015(),
                    [-70.0, -9.0, -69.9, -8.9], predictors, contract,
                )
                exporter.validate_product()
            self.assertEqual(len(list(product.rglob("*.json"))), 5)
            self.assertTrue((product / "grid.geojson").is_file())

    def test_public_product_when_present(self):
        if not (exporter.PRODUTO / "manifest.json").exists():
            self.skipTest("produto anual ainda em processamento")
        exporter.validate_product()


if __name__ == "__main__":
    unittest.main()
