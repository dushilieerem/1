import unittest
from unittest.mock import MagicMock, patch

from services.quant_factor import imports


def factor(i, library='主因子库'):
    return {'library': library, 'factor_id': f'F{i}', 'name': f'因子{i}',
            'display_name': f'显示{i}', 'description': f'说明{i}'}


class MetadataTest(unittest.TestCase):
    def test_rows_keep_name_definition_and_hash(self):
        rows = imports._metadata_rows({'ok': True, 'errors': [], 'factors': [factor(1)]})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source_library'], '主因子库')
        self.assertEqual(rows[0]['source_factor_id'], 'F1')
        self.assertEqual(rows[0]['factor_name'], '因子1')
        self.assertIn('说明1', rows[0]['definition'])
        self.assertEqual(rows[0]['definition_source'], '源码不可见（RE 内置）')
        self.assertEqual(len(rows[0]['import_hash']), 64)

    def test_incomplete_or_duplicate_catalog_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '不完整'):
            imports._metadata_rows({'ok': False, 'errors': ['x'], 'factors': [factor(1)]})
        with self.assertRaisesRegex(ValueError, '重复'):
            imports._metadata_rows({'ok': True, 'errors': [], 'factors': [factor(1), factor(1)]})
        bad = factor(2); bad.pop('name')
        with self.assertRaisesRegex(ValueError, '缺少'):
            imports._metadata_rows({'ok': True, 'errors': [], 'factors': [bad]})


class SyncTest(unittest.TestCase):
    def test_idempotent_upsert_counts_insert_update_unchanged(self):
        rows = imports._metadata_rows({'ok': True, 'errors': [], 'factors': [factor(1), factor(2)]})
        cursor = MagicMock(); cursor.execute.return_value = cursor
        cursor.fetchall.return_value = [
            {'source_library': '主因子库', 'source_factor_id': 'F1', 'import_hash': rows[0]['import_hash']},
            {'source_library': '主因子库', 'source_factor_id': 'F2', 'import_hash': 'old'},
        ]
        connection = MagicMock(); connection.__enter__.return_value = cursor
        with patch.object(imports, 'fetch_re_catalog', return_value={'ok': True, 'errors': [], 'factors': [factor(1), factor(2)]}), \
             patch.object(imports, 'get_conn', return_value=connection):
            result = imports.sync_existing(7, 9)
        self.assertEqual(result['inserted'], 0)
        self.assertEqual(result['updated'], 1)
        self.assertEqual(result['unchanged'], 1)
        self.assertEqual(result['catalog_count'], 2)
        self.assertFalse(result['count_matches'])
        inserts = [call for call in cursor.execute.call_args_list if 'INSERT INTO quant_factor_imported_factors' in call.args[0]]
        self.assertEqual(len(inserts), 1)


if __name__ == '__main__':
    unittest.main()


class ReferenceInventoryTest(unittest.TestCase):
    def test_existing_panel_rows_are_labelled_as_reference_only(self):
        base = {'id': 'a', 'source_library': '主因子库', 'source_factor_id': 'F1', 'factor_name': 'f1',
                'display_name': 'F1', 'definition': 'd', 'category': '动量因子', 'status': 'imported_unreviewed',
                'metrics_status': 'pending'}
        rows = [
            {**base, 'reference_universe': 'CSI300', 'reference_period': '3y',
             'reference_filter_limit_up': 1, 'reference_filter_suspended': 1,
             'reference_rules_version': 'yg_v1', 'reference_rank_ic': 0.04,
             'reference_ic_mean': 0.03, 'reference_ir': 0.5, 'reference_turnover': 0.2,
             'reference_coverage_pool': 0.9, 'reference_computed_at': '2026-11-01'},
            {**base, 'id': 'b', 'source_factor_id': 'F2', 'factor_name': 'f2',
             'reference_universe': None, 'reference_period': None,
             'reference_filter_limit_up': None, 'reference_filter_suspended': None,
             'reference_rules_version': None, 'reference_rank_ic': None,
             'reference_ic_mean': None, 'reference_ir': None, 'reference_turnover': None,
             'reference_coverage_pool': None, 'reference_computed_at': None},
        ]
        cursor = MagicMock(); cursor.execute.return_value = cursor
        cursor.fetchall.return_value = rows
        connection = MagicMock(); connection.__enter__.return_value = cursor
        with patch.object(imports, 'get_conn', return_value=connection):
            out = imports.reference_inventory(7, 9)
        self.assertEqual((out['total'], out['found'], out['missing']), (2, 1, 1))
        self.assertEqual(out['items'][0]['reference']['rule_version'], 'yg_v1')
        self.assertIn('不是 import-benchmark-v1', out['items'][0]['reference']['note'])
        self.assertIsNone(out['items'][1]['reference'])
        self.assertEqual(out['items'][0]['metrics_status'], 'pending')


class ReferenceRangeTest(unittest.TestCase):
    def test_out_of_range_rank_ic_is_not_displayed_as_rank_ic(self):
        row = {'id': 'a', 'source_library': '主因子库', 'source_factor_id': 'F1', 'factor_name': 'f1',
               'display_name': 'F1', 'definition': 'd', 'category': '动量因子',
               'status': 'imported_unreviewed', 'metrics_status': 'pending',
               'reference_universe': 'CSI300', 'reference_period': '3y',
               'reference_filter_limit_up': 1, 'reference_filter_suspended': 1,
               'reference_rules_version': 'yg_v1', 'reference_rank_ic': 880.0,
               'reference_ic_mean': 1, 'reference_ir': 1, 'reference_turnover': 0.2,
               'reference_coverage_pool': None, 'reference_computed_at': None}
        cursor = MagicMock(); cursor.execute.return_value = cursor; cursor.fetchall.return_value = [row]
        connection = MagicMock(); connection.__enter__.return_value = cursor
        with patch.object(imports, 'get_conn', return_value=connection):
            out = imports.reference_inventory(1, 2)
        ref = out['items'][0]['reference']
        self.assertIsNone(ref['rank_ic'])
        self.assertEqual(ref['rank_ic_raw'], 880.0)
        self.assertIn('口径', ref['rank_ic_note'])
