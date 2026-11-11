import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.quant_factor import agent_v0


class FakeConn:
    def __init__(self, active=None, topic=None, branch=None):
        self.active = active
        self.topic = topic
        self.branch = branch
        self.writes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        if 'quant_factor_f0_runs' in sql:
            self.row = self.active
        elif 'quant_factor_topics' in sql:
            self.row = self.topic
        elif 'quant_factor_branches' in sql:
            self.row = self.branch
        elif 'UPDATE detect_projects' in sql:
            self.writes.append((sql, params))
            self.row = None
        else:
            self.row = None
        return self

    def fetchone(self):
        return self.row


class AgentV0Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        state = patch.object(agent_v0, '_STATE_PATH', Path(self.tmp.name) / 'state.json')
        state.start()
        self.addCleanup(state.stop)
        control = patch.object(agent_v0.service, 'control_status', return_value={'paused': False})
        control.start()
        self.addCleanup(control.stop)
        self.pending = None
        pending = patch.object(agent_v0, '_pending_project', side_effect=lambda c, uid: self.pending)
        pending.start()
        self.addCleanup(pending.stop)

    def test_baseline_is_40_symbols_with_5_trials_and_1_seal(self):
        cfg = agent_v0._baseline_config()
        self.assertEqual(len(cfg['researchUniverseSymbols']), 40)
        self.assertEqual(cfg['researchPlan']['maxTrials'], 5)
        self.assertEqual(cfg['researchPlan']['fieldRestriction'], 'ohlcv')
        self.assertEqual(cfg['agentV0']['version'], 'agent-v0')

    def test_enable_without_data_creates_one_pending_project_and_waits(self):
        project = {'id': 'p1', 'name': 'Agent 自主研究：短周期反转基线', 'config': {'agentV0': {'version': 'agent-v0'}}}
        conn = FakeConn()
        def create_project(*args, **kwargs):
            self.pending = project
            return project
        with patch.object(agent_v0, 'get_conn', return_value=conn), \
             patch.object(agent_v0, '_create_baseline_project', side_effect=create_project) as create_project_mock, \
             patch.object(agent_v0, '_preflight', return_value=(None, '固定数据版本尚未确认')) as preflight, \
             patch.object(agent_v0.ledger, 'create_topic') as create_topic, \
             patch.object(agent_v0.f0, 'start') as start:
            result = agent_v0.enable(1, 2)
        create_project_mock.assert_called_once()
        preflight.assert_called_once()
        create_topic.assert_not_called()
        start.assert_not_called()
        self.assertTrue(result['enabled'])
        self.assertEqual(result['state'], 'waiting_data')
        self.assertEqual(result['pending']['project_id'], 'p1')
        state = json.loads((Path(self.tmp.name) / 'state.json').read_text())
        self.assertEqual(state['last_state'], 'waiting_data')

    def test_tick_does_not_start_while_a_run_is_active(self):
        with patch.object(agent_v0, '_read_state', return_value={'enabled': True, 'user_id': 1, 'org_id': 2}), \
             patch.object(agent_v0, 'get_conn', return_value=FakeConn(active={'id': 'run'})), \
             patch.object(agent_v0, '_create_baseline_project') as create:
            result = agent_v0.tick(1, 2)
        self.assertEqual(result['state'], 'running')
        create.assert_not_called()

    def test_tick_creates_topic_and_starts_one_run_when_data_ready(self):
        project = {'id': 'p1', 'name': 'Agent 自主研究：短周期反转基线', 'config': {'agentV0': {'version': 'agent-v0'}}}
        conn = FakeConn(topic=None, branch={'id': 'b1'})
        with patch.object(agent_v0, '_read_state', return_value={'enabled': True, 'user_id': 1, 'org_id': 2}), \
             patch.object(agent_v0, '_pending_project', return_value=project), \
             patch.object(agent_v0, '_project', return_value=project), \
             patch.object(agent_v0, '_preflight', return_value=({'view_id': 'v'}, None)), \
             patch.object(agent_v0, 'get_conn', return_value=conn), \
             patch.object(agent_v0.ledger, 'create_topic', return_value={'topic': {'id': 't1'}}) as create_topic, \
             patch.object(agent_v0.f0, 'start', return_value={'status': 'queued', 'id': 'r1'}) as start:
            result = agent_v0.tick(1, 2)
        create_topic.assert_called_once()
        start.assert_called_once_with(1, 2, 't1', 'b1', 'agent-v0:t1')
        self.assertEqual(result['state'], 'running')
        self.assertEqual(result['run']['id'], 'r1')
        self.assertTrue(conn.writes)
        self.assertIn('jsonb_set', conn.writes[0][0])

    def test_disable_turns_switch_off_without_stopping_the_run(self):
        Path(self.tmp.name, 'state.json').write_text(json.dumps({'enabled': True, 'user_id': 1, 'org_id': 2}))
        with patch.object(agent_v0, '_public_state', return_value={'enabled': False, 'state': 'not_enabled'}):
            out = agent_v0.disable(1, 2)
        self.assertFalse(out['enabled'])
        state = json.loads((Path(self.tmp.name) / 'state.json').read_text())
        self.assertFalse(state['enabled'])


if __name__ == '__main__':
    unittest.main()

