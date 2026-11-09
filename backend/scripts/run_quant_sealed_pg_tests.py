"""Explicit dev-only unique-schema PG checks, separate from isolated unit tests."""
import os,sys
from pathlib import Path
if sys.argv[1:]!=['--allow-isolated-dev']:raise SystemExit('Use --allow-isolated-dev; only unique fixture schema in svquant_dev is permitted')
root=Path(__file__).resolve().parents[1];os.chdir(root);sys.path.insert(0,str(root))
os.environ['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1';os.environ['QUANT_FACTOR_PG_INTEGRATION']='1'
import pytest
prefix='tests/test_quant_factor_sealed_pg.py::IsolatedSealedPostgresTests::'
raise SystemExit(pytest.main([prefix+'test_sealed_parallel_request_replays_same_row_even_at_full_budget',prefix+'test_sealed_intent_insert_rolls_back_on_response_before_commit_failure',prefix+'test_sealed_recovery_workers_claim_only_once','-q']))
