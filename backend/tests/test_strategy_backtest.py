import unittest
from services import strategy_backtest as sb


def factor(code='def f(self):\n    return self.close'):
    return {'factor': 'f', 'code': code}


class BuildCodeTest(unittest.TestCase):
    def test_embeds_source_and_direction(self):
        code = sb.build_code({'factors': [factor(), {**factor(), 'direction': 'negative'}],
                              'top_n': 30, 'rebalance_days': 10})
        self.assertIn('class RecipeStrategy', code)
        self.assertIn('TopN(30)', code)
        self.assertIn('EveryNTradingDays(10)', code)
        self.assertIn('self.factor_0() + -self.factor_1()', code)

    def test_rejects_missing_source(self):
        with self.assertRaisesRegex(ValueError, '没有源码'):
            sb.build_code({'factors': [{'factor': 'imported'}], 'top_n': 30, 'rebalance_days': 10})
