from __future__ import annotations
import json
import unittest
import numpy as np
import exportar_clima_2025 as climate
from pipeline import geo

class Climate2025Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = climate.OUTPUT
        cls.manifest = json.loads((root / "manifest.json").read_text())
        cls.grid = json.loads((root / "grid.geojson").read_text())
        cls.scars = json.loads((root / "scars.geojson").read_text())
        cls.matrices = {name: json.loads((root / f"{name}.json").read_text()) for name in ("humidity", "precipitation")}

    def test_contract_and_complete_year(self):
        climate.validate_product(self.manifest, self.grid, self.matrices, self.scars)
        self.assertEqual(self.manifest["dates"][0], "2025-01-01")
        self.assertEqual(self.manifest["dates"][-1], "2025-12-31")
        self.assertGreater(len(self.scars["features"]), 0)
        for i, count in enumerate(self.manifest["n_valid_pixels"]):
            if count == 0:
                for matrix in self.matrices.values():
                    self.assertTrue(all(day[i] == [None, None, None] for day in matrix["values"]))

    def test_sampled_spatial_statistics_match_rasters(self):
        selected = next(i for i, n in enumerate(self.manifest["n_valid_pixels"]) if n >= 5)
        feature = self.grid["features"][selected]
        for name, path in (("humidity", climate.HUMIDITY), ("precipitation", climate.RAINFALL)):
            cube = climate.read_year(path)
            grid = geo.ler_grade(str(path))
            members = climate.climate_membership([feature], grid, np.isfinite(cube).any(axis=2))[0]
            weights = np.array([w for _, _, w in members])
            for date in ("2025-01-01", "2025-08-25", "2025-12-31"):
                band = self.manifest["dates"].index(date)
                values = np.array([cube[r, c, band] for r, c, _ in members])
                expected = [round(float(values.min()), 3), round(float(np.average(values, weights=weights)), 3), round(float(values.max()), 3)]
                self.assertEqual(self.matrices[name]["values"][band][selected], expected)

    def test_truncated_matrix_rejected(self):
        broken = {**self.matrices, "humidity": {"values": self.matrices["humidity"]["values"][:-1]}}
        with self.assertRaises(ValueError):
            climate.validate_product(self.manifest, self.grid, broken, self.scars)

if __name__ == "__main__":
    unittest.main()
