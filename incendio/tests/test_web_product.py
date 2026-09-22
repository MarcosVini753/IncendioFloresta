from __future__ import annotations

import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import exportar_suscetibilidade as exporter


class ExportedProductTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (exporter.AGREGADO / "manifest.json").open(encoding="utf-8") as stream:
            cls.manifest = json.load(stream)
        with (exporter.AGREGADO / "mapa.geojson").open(encoding="utf-8") as stream:
            cls.collection = json.load(stream)

    def test_public_contract_and_score_domain(self):
        self.assertEqual(self.manifest["schema_version"], "1.0")
        self.assertEqual(self.manifest["product"], "wildfire_susceptibility")
        self.assertEqual(self.manifest["default_model"], "gradboost")
        self.assertEqual(self.manifest["value"]["semantics"], "relative_score")
        self.assertEqual(len(self.manifest["models"]), 4)
        features = self.collection["features"]
        self.assertEqual(len(features), self.manifest["counts"]["features"])
        self.assertEqual(
            sum(item["properties"]["n_source_cells"] for item in features),
            307_410,
        )
        for feature in features:
            for column in exporter.SCORE_COLUMNS:
                score = feature["properties"][column]
                self.assertTrue(math.isfinite(score))
                self.assertGreaterEqual(score, 0)
                self.assertLessEqual(score, 1)

    def test_sampled_aggregates_equal_source_means(self):
        scores = pd.read_parquet(exporter.CACHE_SCORES)
        boundary = exporter.carregar_limite()
        bounds = exporter.geometry_bounds(boundary["geometry"])
        rows, columns = exporter.sector_indices(scores["lon"], scores["lat"], bounds)
        scores = scores.assign(_row=rows, _column=columns)
        by_id = {item["properties"]["id"]: item["properties"] for item in self.collection["features"]}
        samples = self.collection["features"][:: max(len(self.collection["features"]) // 7, 1)][:7]
        for feature in samples:
            cell_id = feature["properties"]["id"]
            row = int(cell_id[4:6]) - 1
            column = int(cell_id[7:9]) - 1
            source = scores[(scores["_row"] == row) & (scores["_column"] == column)]
            self.assertEqual(len(source), by_id[cell_id]["n_source_cells"])
            for score_column in exporter.SCORE_COLUMNS:
                self.assertAlmostEqual(
                    by_id[cell_id][score_column],
                    round(float(source[score_column].mean()), 7),
                    places=7,
                )

    def test_non_finite_or_out_of_domain_scores_are_rejected(self):
        valid = pd.DataFrame({column: [0.5] for column in exporter.SCORE_COLUMNS})
        for invalid in (np.nan, -0.01, 1.01):
            candidate = valid.copy()
            candidate.loc[0, exporter.SCORE_COLUMNS[0]] = invalid
            with self.assertRaises(ValueError):
                exporter.validar_scores(candidate)

    def test_missing_boundary_has_actionable_error(self):
        missing = Path("/tmp/nonexistent-acre-boundary.geojson")
        with patch.object(exporter, "LIMITE", missing):
            with self.assertRaisesRegex(FileNotFoundError, "Limite ausente"):
                exporter.carregar_limite()


if __name__ == "__main__":
    unittest.main()
