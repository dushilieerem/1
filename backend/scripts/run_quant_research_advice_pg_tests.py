"""Explicit bounded own-schema tests; direct/pooled DB and network escape guards."""
import os,sys,inspect,socket
from pathlib import Path
from unittest.mock import patch
if sys.argv[1:]!=['--allow-isolated-dev']:raise SystemExit('Explicit isolated development schema flag required')
root=Path(__file__).resolve().parents[1];os.chdir(root);sys.path.insert(0,str(root))
os.environ['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1';os.environ['QUANT_FACTOR_PG_INTEGRATION']='1'
import psycopg,pytest
from services.core import db
native_connect=psycopg.connect;original_socket_connect=socket.socket.connect
fixture=(root/'tests/test_quant_factor_assets_pg.py').resolve()
def connect(*args,**kwargs):
 caller=Path(inspect.currentframe().f_back.f_code.co_filename).resolve()
 if caller!=fixture:raise AssertionError('OWNED ADVICE PG: real connect outside explicit fixture prohibited')
 return native_connect(*args,**kwargs)
def forbidden(*a,**k):raise AssertionError('OWNED ADVICE PG: pooled/public DB or network prohibited')
def network(sock,*a,**k):
 if sock.family in (socket.AF_INET,socket.AF_INET6):return forbidden()
 return original_socket_connect(sock,*a,**k)
prefix='tests/test_quant_research_advice_pg.py::AdviceReceiptPostgresTests::'
names=['test_commit_then_lost_response_replays_after_stop_and_new_run_without_rewrite','test_same_key_different_message_branch_epoch_or_run_is_conflict','test_permission_scope_and_new_run_same_branch_cannot_accept_old_target','test_branch_changed_is_definite_no_write_and_explicit_new_target_can_save_once']
with patch.object(psycopg,'connect',connect),patch.object(db,'_borrow_conn',side_effect=forbidden),patch.object(socket.socket,'connect',network),patch.object(socket,'create_connection',side_effect=forbidden):raise SystemExit(pytest.main([*(prefix+name for name in names),'tests/test_quant_research_method_pg.py::IsolatedResearchMethodPostgresTests::test_advice_response_loss_idempotent_and_stale_target_rejected','-q']))
