import math
import unittest
from unittest.mock import patch

from services.quant_factor import import_metrics
from services.quant_factor.metrics import newey_west_t

ROW = {'id': 'f1', 'factor_name': 'factor', 'source_library': '主因子库'}
SNAPSHOT = {'view_id': 'research-rv-20261105-1', 'view_manifest_sha256': 'm' * 64,
            'contract_revision': '2026-11-04c', 'as_of': '2026-11-04',
            'release_ids': {'daily_bars': 'r1'}, 'datasets': {}}


def series(n=120):
    return [{'date': f'd{i}', 'value': 0.03 + 0.02 * math.sin(i / 3)} for i in range(n)]


class RequestTest(unittest.TestCase):
    def test_fixed_benchmark_fields(self):
        payload = import_metrics.request_payload(ROW)
        self.assertEqual(payload['library_name'], '主因子库')
        self.assertEqual(payload['factor_name'], 'factor')
        for key, value in (('universe', 'CSI300'), ('benchmark', 'CSI300'),
                           ('start', '2022-01-01'), ('end', '2024-12-31'),
                           ('holding_period', 1), ('execution_timing', 'next_open'),
                           ('groups', 5), ('rebalance_days', 1), ('direction', 'raw')):
            self.assertEqual(payload[key], value)


class EvaluateTest(unittest.TestCase):
    def test_missing_rank_ic_series_stays_pending_with_reason(self):
        result = import_metrics.evaluate_result(ROW, {'metrics': {'rank_ic': 0.01}}, SNAPSHOT)
        self.assertEqual(result['metrics_status'], 'pending')
        self.assertIn('R1', result['reason'])
        self.assertIn('rank_ic_series', result['evidence']['missing'])

    def test_ok_requires_rank_ic_turnover_and_uses_real_series(self):
        data = {'metrics': {'turnover': 0.31}, 'factor_analysis': {'rank_ic_series': series(), 'rank_ic_mean': 0.04, 'coverage': 0.97}}
        result = import_metrics.evaluate_result(ROW, data, SNAPSHOT)
        self.assertEqual(result['metrics_status'], 'ok')
        self.assertAlmostEqual(result['metrics']['newey_west_t'], newey_west_t(series())['t'], places=12)
        self.assertEqual(result['metrics']['valid_days'], 120)
        self.assertEqual(result['metrics']['turnover'], 0.31)

    def test_missing_turnover_is_not_ok(self):
        data = {'factor_analysis': {'rank_ic_series': series(), 'rank_ic_mean': 0.04}}
        result = import_metrics.evaluate_result(ROW, data, SNAPSHOT)
        self.assertEqual(result['metrics_status'], 'pending')
        self.assertIn('换手', result['reason'])

    def test_constant_series_is_not_computable(self):
        data = {'factor_analysis': {'rank_ic_series': [{'value': 0.0}] * 10, 'rank_ic_mean': 0.0}, 'metrics': {'turnover': 0.2}}
        result = import_metrics.evaluate_result(ROW, data, SNAPSHOT)
        self.assertEqual(result['metrics_status'], 'not_computable')


class SnapshotTest(unittest.TestCase):
    def test_snapshot_records_view_releases_manifest_and_as_of(self):
        view = {'view_id': 'research-rv-20261105-1', 'manifest_sha256': 'a' * 64,
                'contract_version': '2026-11-04c',
                'datasets': {'daily_bars': {'release': 'r1', 'date_max': '2026-11-04'},
                             'industry': {'release': 'r2', 'date_max': '2026-11-03'}}}
        with patch.object(import_metrics, 'published_view', return_value=view):
            snap = import_metrics.view_snapshot()
        self.assertEqual(snap['view_id'], 'research-rv-20261105-1')
        self.assertEqual(snap['as_of'], '2026-11-04')
        self.assertEqual(snap['release_ids'], {'daily_bars': 'r1', 'industry': 'r2'})
        self.assertEqual(snap['view_manifest_sha256'], 'a' * 64)


if __name__ == '__main__':
    unittest.main()
