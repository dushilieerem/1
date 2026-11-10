"""Explicit owned-schema development transaction checks, never ordinary test discovery."""
import os,sys
from pathlib import Path
if sys.argv[1:]!=['--allow-isolated-dev']:raise SystemExit('Requires --allow-isolated-dev, unique schema of svquant_dev only')
root=Path(__file__).resolve().parents[1];os.chdir(root);sys.path.insert(0,str(root))
os.environ['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1';os.environ['QUANT_FACTOR_PG_INTEGRATION']='1'
import pytest
prefix='tests/test_quant_research_method_pg.py::IsolatedResearchMethodPostgresTests::'
names=['test_generic_removal_and_recomputed_contract_rollback','test_quant_save_requires_same_server_contract','test_advice_response_loss_idempotent_and_stale_target_rejected']
raise SystemExit(pytest.main([*(prefix+n for n in names),'tests/test_quant_research_method_pg.py::IsolatedNewResearchPostgresTests::test_new_topic_freezes_h1_epoch_then_start_and_human_advice','-q']))
