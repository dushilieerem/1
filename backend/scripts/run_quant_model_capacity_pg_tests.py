import os,sys,socket
from pathlib import Path
from unittest.mock import patch
if sys.argv[1:]!=['--allow-isolated-dev']:raise SystemExit('Requires --allow-isolated-dev')
root=Path(__file__).resolve().parents[1];os.chdir(root);sys.path.insert(0,str(root));os.environ['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1';os.environ['QUANT_FACTOR_PG_INTEGRATION']='1';os.environ.pop('QUANT_RESEARCH_DURABLE_QUEUE',None)
import pytest
from services.core import db
prefix='tests/test_quant_model_capacity_pg.py::IsolatedCapacityTests::'
names=['test_all_three_roles_omit_product_cap_and_freeze_actual_parameters_and_provider_total','test_timeout_preserves_unknown_output_capacity_and_never_reissues_same_call','test_known_length_receipt_is_metered_once_not_a_market_trial','test_received_response_without_usage_remains_unknown_charge_not_zero','test_no_unlimited_authorization_cannot_send_uncapped_role_request','test_large_received_artifact_retains_real_usage_and_known_technical_failure']
original=socket.socket.connect
def forbidden(*a,**k):raise AssertionError('OWNED PG TEST: pooled/public DB and physical network forbidden')
def connect(sock,*a,**k):
 if sock.family in (socket.AF_INET,socket.AF_INET6):return forbidden()
 return original(sock,*a,**k)
with patch.object(db,'_borrow_conn',side_effect=forbidden),patch.object(socket.socket,'connect',connect),patch.object(socket,'create_connection',side_effect=forbidden):raise SystemExit(pytest.main([*(prefix+n for n in names),'-q']))
