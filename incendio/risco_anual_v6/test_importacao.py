"""Contratos de importação: valores recebidos, máscaras e COG sem perdas."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.windows import Window

from incendio.importar_risco_professor_v6 import read_sources, verify_cog, write_cog


class ImportTests(unittest.TestCase):
    def test_nodata_is_excluded_but_zero_is_a_real_value(self):
        data = np.array([[[0, 2, -9999]], [[0, 98, -9999]]], dtype="float32")
        with MemoryFile() as mem:
            with mem.open(driver="GTiff", height=1, width=3, count=2,
                          dtype="float32", nodata=-9999, crs=4326,
                          transform=from_origin(-71, -8, .000269, .000269)) as source:
                source.write(data)
                recovered, mask = read_sources([source], Window(0, 0, 3, 1))
                np.testing.assert_array_equal(mask, [[True, True, False]])
                np.testing.assert_array_equal(recovered, data)
                for bad in (-1, 101, np.inf, np.nan, -9999):
                    broken = data.copy()
                    broken[1, 0, 0] = bad
                    source.write(broken)
                    with self.assertRaises(ValueError):
                        read_sources([source], Window(0, 0, 3, 1))

    def test_two_float32_bands_are_preserved_exactly_including_mask(self):
        data = np.array([[[.12345678, -9999], [0, 9.876543]],
                         [[94.031158, -9999], [50, 98.169739]]], dtype="float32")
        mask = data[0] != -9999
        affine = from_origin(-71, -8, .000269, .000269)
        with tempfile.TemporaryDirectory() as tmp:
            cog = Path(tmp) / "sector.tif"
            write_cog(cog, data, mask, affine, 2026)
            verify_cog(cog, data, mask, affine)
            changed = data.copy()
            changed[1, 0, 0] = 94
            with self.assertRaises(ValueError):
                verify_cog(cog, changed, mask, affine)


if __name__ == "__main__":
    unittest.main()
