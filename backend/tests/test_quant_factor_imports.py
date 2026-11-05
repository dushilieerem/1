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
