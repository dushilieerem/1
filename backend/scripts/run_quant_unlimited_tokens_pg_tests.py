"""Explicit six bounded development-schema transactions, no live institution writes."""
import os,sys
from pathlib import Path
if sys.argv[1:]!=['--allow-isolated-dev']:raise SystemExit('Requires --allow-isolated-dev')
root=Path(__file__).resolve().parents[1];os.chdir(root);sys.path.insert(0,str(root))
os.environ['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1';os.environ['QUANT_FACTOR_PG_INTEGRATION']='1'
import pytest
prefix='tests/test_quant_unlimited_tokens_pg.py::IsolatedUnlimitedTests::'
names=['test_unlimited_replay_preserves_old_grant_spend_and_unknown_history','test_one_institution_pool_shared_actors_but_other_institution_is_not_authorized','test_unknown_current_usage_stays_unresolved_and_replay_cannot_resend','test_unlimited_does_not_expand_shared_account_daily_calls','test_changed_authorization_is_rejected_and_original_event_remains','test_without_new_authorization_old_finite_policy_still_blocks','test_closed_or_replaced_grant_is_waiting_not_a_status_crash_or_false_ready']
raise SystemExit(pytest.main([*(prefix+n for n in names),'-q']))
