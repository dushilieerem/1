import unittest

from services import strategy_research as svc


class RecipeTest(unittest.TestCase):
    def test_valid_recipe(self):
        rc = svc.recipe({'factors': [{'factor': 'f1'}], 'top_n': 30, 'rebalance_days': 10})
        self.assertEqual(rc['factors'], [{'factor': 'f1', 'direction': 'positive', 'library': '主因子库'}])
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


class BranchGuardTest(unittest.TestCase):
    def call(self, source='agent', topic_view='v', current='v'):
        from unittest.mock import MagicMock, patch
        c = MagicMock(); c.execute.return_value = c
        c.fetchone.return_value = {'id': 't', 'view_id': topic_view}
        conn = MagicMock(); conn.__enter__.return_value = c
        with patch.object(svc, 'get_conn', return_value=conn), \
             patch.object(svc, 'published_view', return_value={'view_id': current, 'datasets': {}}):
            svc.create_branch(1, 2, 't', {'source': source, 'hypothesis': 'h', 'factors': ['f'],
                                          'top_n': 30, 'rebalance_days': 10})

    def test_public_entry_rejects_agent_source(self):
        from unittest.mock import MagicMock, patch
        c = MagicMock(); c.execute.return_value = c; c.fetchone.return_value = {'id': 't', 'view_id': 'v'}
        conn = MagicMock(); conn.__enter__.return_value = c
        with patch.object(svc, 'get_conn', return_value=conn), patch.object(svc, 'published_view', return_value={'view_id': 'v', 'datasets': {}}):
            with self.assertRaisesRegex(ValueError, '来源'):
                svc.create_branch(1, 2, 't', {'source': 'agent', 'hypothesis': 'h', 'factors': ['f'], 'top_n': 30, 'rebalance_days': 10})

    def test_view_drift_rejected(self):
        with self.assertRaisesRegex(ValueError, '视图'):
            self.call(topic_view='old', current='new')

    def test_buffer_range(self):
        with self.assertRaisesRegex(ValueError, 'buffer'):
            svc.recipe({'factors': ['f'], 'top_n': 30, 'rebalance_days': 10, 'buffer': 2})


class SourceRecipeTest(unittest.TestCase):
    def test_source_is_kept_and_validated(self):
        rc = svc.recipe({'factors': [{'factor': 'f', 'code': 'def f(self):\n    return self.close'}],
                         'top_n': 30, 'rebalance_days': 10})
        self.assertIn('code', rc['factors'][0])
        with self.assertRaises(ValueError):
            svc.recipe({'factors': [{'factor': 'f', 'code': 'def f(self):\n    return ('}],
                        'top_n': 30, 'rebalance_days': 10})


class ImportedAssetTest(unittest.TestCase):
    def test_importable_hides_owner_ids(self):
        from unittest.mock import MagicMock, patch
        c = MagicMock()
        c.execute.return_value.fetchall.return_value = [
            {'id': 'p1', 'name': '平台动量', 'description': '', 'run_count': 2,
             'updated_at': '2026-11-01', 'imported': False, 'user_id': 9, 'org_id': 2}]
        conn = MagicMock(); conn.__enter__.return_value = c
        with patch.object(svc, 'get_conn', return_value=conn):
            rows = svc.importable(9, 2)
        self.assertEqual(rows[0]['id'], 'p1')
        self.assertNotIn('user_id', rows[0])
        self.assertNotIn('org_id', rows[0])

    def test_import_requires_owned_project_and_hashes_config(self):
        from unittest.mock import MagicMock, patch
        c = MagicMock()
        project = MagicMock(); project.fetchone.return_value = {'name': '平台动量', 'config': {'top_n': 30}}
        insert = MagicMock()
        stored = MagicMock(); stored.fetchone.return_value = {
            'id': 'a1', 'user_id': 9, 'org_id': 2, 'source_project_id': 'p1',
            'name': '平台动量', 'config': {'top_n': 30}, 'implementation_hash': 'h',
            'status': 'imported', 'imported_at': '2026-11-01'}
        c.execute.side_effect = [project, insert, stored]
        conn = MagicMock(); conn.__enter__.return_value = c
        with patch.object(svc, 'get_conn', return_value=conn):
            out = svc.import_asset(9, 2, 'p1')
        self.assertEqual(out['name'], '平台动量')
        self.assertNotIn('user_id', out)
        params = c.execute.call_args_list[1].args[1]
        self.assertEqual(len(params[6]), 64)
        self.assertEqual(params[3], 'p1')

    def test_import_missing_project_raises_keyerror(self):
        from unittest.mock import MagicMock, patch
        c = MagicMock(); c.execute.return_value.fetchone.return_value = None
        conn = MagicMock(); conn.__enter__.return_value = c
        with patch.object(svc, 'get_conn', return_value=conn):
            with self.assertRaises(KeyError):
                svc.import_asset(9, 2, 'missing')
