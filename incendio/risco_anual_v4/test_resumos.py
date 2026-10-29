import unittest
import numpy as np
from incendio.risco_anual_v4.exportar_resumos import exact_quantiles, weighted_summaries, group_key


class SummaryTests(unittest.TestCase):
    def test_exact_quantile_convention_including_small_groups(self):
        for data in ([94.25], [10., 98.], [100., 0., 95., 70., 50., 90.]):
            values = np.array(data, dtype='float32')
            expected = [sorted(data)[int(np.ceil(q*len(data)))-1] for q in (.5,.75)]
            self.assertEqual(exact_quantiles(values), expected)
        with self.assertRaises(ValueError):
            exact_quantiles(np.array([], dtype='float32'))

    def test_rarity_weights_ignore_absent_classes(self):
        counts = np.array([0,9,1,0,0])
        sums = np.array([0.,9*60.,1*80.,0.,0.])
        local, state = weighted_summaries(counts,sums,np.array([0.,.9,.1,0.,0.]))
        self.assertEqual(local,70.)
        self.assertEqual(state,70.)
        # All pixels equal: weights must preserve the observed level.
        local,state = weighted_summaries(np.array([0,0,0,0,3]),np.array([0.,0.,0.,0.,291.]),np.array([.5,.2,.2,.05,.05]))
        self.assertEqual(local,97.)
        self.assertEqual(state,97.)

    def test_negative_easting_ids_preserve_source_group(self):
        self.assertEqual(group_key('AC-5KM-E-11N1832'),-108168)
        self.assertEqual(group_key('AC-5KM-E105N1773'),1051773)
        with self.assertRaises(ValueError): group_key('wrong')


if __name__=='__main__': unittest.main()
