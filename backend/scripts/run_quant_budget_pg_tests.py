"""Explicit realPG tests in unique owned schema; not regular network-enabled pytest."""
import os,sys
from pathlib import Path
if sys.argv[1:]!=['--allow-isolated-dev']:raise SystemExit('Requires --allow-isolated-dev')
root=Path(__file__).resolve().parents[1];os.chdir(root);sys.path.insert(0,str(root));os.environ['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1';os.environ['QUANT_FACTOR_PG_INTEGRATION']='1'
import pytest
prefix='tests/test_quant_model_budget_pg.py::IsolatedBudgetPostgresTests::'
names=['test_settled_receipt_cannot_be_replaced_with_different_usage','test_authorization_activation_same_org_scope_is_one_pool_without_resetting_spend','test_real_runner_persists_response_then_replays_without_second_physical_request','test_real_runner_lost_response_cannot_automatically_resubmit','test_durable_reservation_replay_after_lost_response_is_one_charge','test_parallel_reservations_cannot_overspend_one_org_pool','test_members_share_one_pool_but_other_org_cannot_inherit','test_claim_is_atomic_and_account_call_count_preserved','test_provider_total_settlement_and_replay_are_not_double_charged','test_timeout_and_missing_usage_keep_full_reservation','test_old_baseline_unknown_blocks_without_grant_even_with_known_lower_bound','test_account_daily_limit_is_not_expanded_by_grant']
raise SystemExit(pytest.main([*(prefix+n for n in names),'-q']))
