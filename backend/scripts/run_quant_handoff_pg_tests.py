"""Explicit owned-schema development transaction checks, never ordinary test discovery."""
import os,sys
from pathlib import Path
if sys.argv[1:]!=['--allow-isolated-dev']:raise SystemExit('Requires --allow-isolated-dev, unique schema of svquant_dev only')
root=Path(__file__).resolve().parents[1];os.chdir(root);sys.path.insert(0,str(root))
os.environ['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1';os.environ['QUANT_FACTOR_PG_INTEGRATION']='1'
import pytest
prefix='tests/test_quant_factor_handoff_pg.py::IsolatedHandoffPostgresTests::'
names=['test_stale_takeover_cas_does_not_replace_new_manual_branch','test_old_f3_pending_takeover_save_and_late_ready_does_not_block_or_overwrite','test_parallel_manual_saves_same_epoch_allow_exactly_one','test_takeover_forks_exact_frozen_source_and_preserves_old_evidence_and_k','test_manual_save_rejects_stale_epoch_and_rolls_back','test_late_old_model_cannot_overwrite_after_real_pause_and_takeover','test_handoff_commit_then_lost_response_replays_same_queue_and_budget','test_handoff_insert_failure_rolls_back_control_epoch_and_queue']
raise SystemExit(pytest.main([*(prefix+n for n in names),'-q']))
