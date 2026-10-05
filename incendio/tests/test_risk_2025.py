from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
import exportar_risco_2025 as exporter
from risco_anual import geometria as web
from risco_anual.pipeline import modelos

class AnnualRiskTest(unittest.TestCase):
    def test_checkpoints_require_provenance_and_domain(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.npy"
            metadata = {"cell_count": 3, "seed": 42}
            self.assertFalse(exporter.checkpoint_valid(path, metadata))
            np.save(path, np.array([0.1, 0.5, 1.0]))
            web._json_dump(path.with_suffix(".json"), metadata)
            self.assertTrue(exporter.checkpoint_valid(path, metadata))
            self.assertFalse(exporter.checkpoint_valid(path, {**metadata, "seed": 1}))
            np.save(path, np.array([0.1, np.nan, 1.0]))
            self.assertFalse(exporter.checkpoint_valid(path, metadata))
            with path.with_suffix(".json").open("w") as stream:
                stream.write("{")
            self.assertFalse(exporter.checkpoint_valid(path, metadata))

    def test_exact_fuzzy_is_independent_of_batch_size(self):
        rng = np.random.default_rng(42)
        train, query = rng.normal(size=(150, 6)), rng.normal(size=(25, 6))
        target = np.arange(150) % 2
        small = modelos.FuzzyKNN(k=29, m=2, bloco=7).fit(train, target)
        large = modelos.FuzzyKNN(k=29, m=2, bloco=512).fit(train, target)
        np.testing.assert_allclose(small.predict_proba(query), large.predict_proba(query), atol=1e-12)

    def test_public_product_and_all_aggregated_means(self):
        scores = pd.read_parquet(exporter.BASE / "resultados/risco_2025/scores_2025.parquet")
        exporter.validate_scores(scores)
        exporter.validate_product(scores=scores)
        manifest = json.loads((exporter.OUTPUT / "aggregated/manifest.json").read_text())
        self.assertEqual(manifest["default_model"], "random_forest")
        self.assertEqual(manifest["default_scenario"], "regional")
        self.assertEqual(len(manifest["models"]), 5)
        self.assertEqual(len(manifest["scenarios"]), 2)
        self.assertEqual(manifest["training"]["train_years"], [2007, 2024])
        self.assertEqual(manifest["training"]["climate_year"], 2024)
        self.assertEqual(manifest["evaluation"]["test_positive_cells"], 39)

    def test_invalid_score_rejected(self):
        scores = pd.read_parquet(exporter.BASE / "resultados/risco_2025/scores_2025.parquet")
        for invalid in (float("nan"), -0.01, 1.01):
            candidate = scores.copy()
            candidate.loc[0, web.SCORE_COLUMNS[0]] = invalid
            with self.assertRaises(ValueError):
                exporter.validate_scores(candidate)

if __name__ == "__main__":
    unittest.main()
