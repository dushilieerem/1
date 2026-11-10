import os,sys
from pathlib import Path
if sys.argv[1:]!=['--allow-isolated-dev']:raise SystemExit('Requires --allow-isolated-dev')
root=Path(__file__).resolve().parents[1];os.chdir(root);sys.path.insert(0,str(root));os.environ['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1';os.environ['QUANT_FACTOR_PG_INTEGRATION']='1'
import pytest
prefix='tests/test_quant_research_queue_pg.py::IsolatedQueueTests::'
names=['test_two_database_claimants_get_one_root_and_children_can_run_while_parent_waits','test_unknown_physical_call_blocks_other_children_and_roots_until_receipt_arrives','test_restart_preserves_queued_and_reclaims_only_proved_dead_owned_owner','test_old_usage_gaps_without_queue_identity_do_not_occupy_slot','test_cancel_queued_keeps_history_and_stale_owner_cannot_finish_current_job','test_resume_waiting_refusal_rolls_back_f0_status_in_same_transaction','test_scheduler_checkpoint_yields_to_older_root_without_ending_research','test_actual_novelty_submit_intent_blocks_slot_even_with_saved_development_result','test_actual_f0_parent_creates_agent_child_and_waits_without_changing_controller','test_actual_development_retry_requeues_original_get_and_unknown_submit_keeps_error','test_explicit_lightweight_advice_is_metered_while_heavy_queue_remains_occupied','test_confirmed_provider_rejection_is_not_an_unknown_running_request']
from unittest.mock import patch
from services.core import db
import socket
original_connect=socket.socket.connect
def forbid(*a,**k):raise AssertionError('OWNED PG TEST: pooled/public database or network access forbidden; use explicit fixture connection')
def connect(sock,*a,**k):
 if sock.family in (socket.AF_INET,socket.AF_INET6):return forbid()
 return original_connect(sock,*a,**k)
with patch.object(db,'_borrow_conn',side_effect=forbid),patch.object(socket.socket,'connect',connect),patch.object(socket,'create_connection',side_effect=forbid):
 raise SystemExit(pytest.main([*(prefix+n for n in names),'-q']))
