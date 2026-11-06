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


class RerunTest(unittest.TestCase):
    def test_same_recipe_returns_rerun_without_calling_re(self):
        from unittest.mock import MagicMock, patch
        from services import strategy_backtest_runner as runner
        branch = {'id': 'b', 'topic_id': 't', 'recipe': {'factors': [{'factor': 'f', 'library': '主因子库'}],
                  'top_n': 30, 'rebalance_days': 10}, 'implementation_hash': 'h'}
        topic = {'id': 't', 'view_id': 'v', 'release_ids': {}, 'view_manifest_sha256': '', 'contract_revision': '', 'as_of': None}
        prior = {'id': 'old', 'trial_no': 1, 'branch_id': 'b', 'implementation_hash': 'h', 'view_id': 'v',
                 'outcome': 'failed', 'metrics': {'annual_return': 0.1}, 'gate': {'checks': []}, 'report_id': 'r1'}
        cursor = MagicMock(); cursor.execute.return_value = cursor
        cursor.fetchone.side_effect = [branch, topic]
        cursor.fetchall.return_value = [prior]
        conn = MagicMock(); conn.__enter__.return_value = cursor
        with patch.object(runner, 'get_conn', return_value=conn), \
             patch.object(runner, 'published_view', return_value={'view_id': 'v'}), \
             patch.object(runner, 'request_json') as req:
            out = runner.run_trial(1, 2, 'b')
        self.assertEqual(out['outcome'], 'rerun')
        self.assertEqual(out['rerun_of'], 'old')
        req.assert_not_called()
