from __future__ import annotations

import json
import unittest

import numpy as np

import exportar_clima_2015 as climate
from pipeline import geo


class ClimateProductTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = climate.OUTPUT
        cls.manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        cls.grid = json.loads((root / "grid.geojson").read_text(encoding="utf-8"))
        cls.scars = json.loads((root / "scars.geojson").read_text(encoding="utf-8"))
        cls.matrices = {
            name: json.loads((root / f"{name}.json").read_text(encoding="utf-8"))
            for name in ("humidity", "precipitation")
        }

    def test_contract_and_daily_coverage(self):
        climate.validate_product(self.manifest, self.grid, self.matrices, self.scars)
        self.assertEqual(len(self.manifest["dates"]), 365)
        self.assertEqual(len(self.manifest["cell_order"]), 212)
        self.assertEqual(len(self.scars["features"]), 425)
        self.assertEqual(sum(count == 0 for count in self.manifest["n_valid_pixels"]), 8)
        for index, count in enumerate(self.manifest["n_valid_pixels"]):
            if count == 0:
                for matrix in self.matrices.values():
                    self.assertTrue(all(day[index] == [None, None, None] for day in matrix["values"]))

    def test_january_august_december_against_rasters(self):
        selected = next(i for i, n in enumerate(self.manifest["n_valid_pixels"]) if n >= 5)
        feature = self.grid["features"][selected]
        checks = ("2015-01-01", "2015-08-25", "2015-12-31")
        for name, path in (("humidity", geo.ARQ_UMIDADE), ("precipitation", geo.ARQ_PRECIPITACAO)):
            cube = geo.ler_cubo(str(climate.BASE / path), dtype=np.float32)
            grid = geo.ler_grade(str(climate.BASE / path))
            members = climate.climate_membership([feature], grid, np.isfinite(cube).any(axis=2))[0]
            self.assertEqual(len(members), self.manifest["n_valid_pixels"][selected])
            weights = np.array([weight for _, _, weight in members])
            for date in checks:
                band = int(np.searchsorted(geo.datas_clima(), np.datetime64(date)))
                values = np.array([cube[row, col, band] for row, col, _ in members])
                expected = [round(float(values.min()), 3), round(float(np.average(values, weights=weights)), 3), round(float(values.max()), 3)]
                day = self.manifest["dates"].index(date)
                self.assertEqual(self.matrices[name]["values"][day][selected], expected)

    def test_invalid_matrix_is_rejected(self):
        broken = {**self.matrices, "humidity": {"values": self.matrices["humidity"]["values"][:-1]}}
        with self.assertRaisesRegex(ValueError, "365 x 212"):
            climate.validate_product(self.manifest, self.grid, broken, self.scars)


if __name__ == "__main__":
    unittest.main()
