import unittest

from services import strategy_research as svc


class RecipeTest(unittest.TestCase):
    def test_valid_recipe(self):
        rc = svc.recipe({'factors': [{'factor': 'f1'}], 'top_n': 30, 'rebalance_days': 10})
        self.assertEqual(rc['factors'], [{'factor': 'f1', 'direction': 'positive'}])
        self.assertTrue(rc['equal_weight'])

    def test_rejects_factor_count_and_bad_direction(self):
        for factors in ([], [{'factor': f'f{i}'} for i in range(4)]):
            with self.assertRaisesRegex(ValueError, '1—3'):
                svc.recipe({'factors': factors, 'top_n': 30, 'rebalance_days': 10})
        with self.assertRaisesRegex(ValueError, '方向'):
            svc.recipe({'factors': [{'factor': 'f', 'direction': 'up'}], 'top_n': 30, 'rebalance_days': 10})

    def test_rejects_bad_size(self):
        with self.assertRaises(ValueError):
            svc.recipe({'factors': ['f'], 'top_n': 3, 'rebalance_days': 10})
        with self.assertRaises(ValueError):
            svc.recipe({'factors': ['f'], 'top_n': 30, 'rebalance_days': 0})
