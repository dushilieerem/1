"""Explicit owned-schema development transaction checks, never ordinary test discovery."""
import os,sys
from pathlib import Path
if sys.argv[1:]!=['--allow-isolated-dev']:raise SystemExit('Requires --allow-isolated-dev, unique schema of svquant_dev only')
root=Path(__file__).resolve().parents[1];os.chdir(root);sys.path.insert(0,str(root))
os.environ['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1';os.environ['QUANT_FACTOR_PG_INTEGRATION']='1'
import pytest
prefix='tests/test_quant_research_run_snapshot_pg.py::IsolatedRunSnapshotTests::'
names=['test_explicit_new_run_preserves_same_topic_h1_k_and_old_failed_record','test_nonmethod_change_can_resume_but_actual_loaded_method_change_cannot','test_data_dependency_wait_preserves_method_snapshot_and_resumes_same_run','test_updated_method_and_manual_handoff_bind_original_epoch_in_one_new_run']
from unittest.mock import patch
from services.core import db
import socket
original=socket.socket.connect
def forbid(*a,**k):raise AssertionError('OWNED PG TEST: pooled/public DB or physical network forbidden')
def connect(sock,*a,**k):
 if sock.family in (socket.AF_INET,socket.AF_INET6):return forbid()
 return original(sock,*a,**k)
with patch.object(db,'_borrow_conn',side_effect=forbid),patch.object(socket.socket,'connect',connect),patch.object(socket,'create_connection',side_effect=forbid):raise SystemExit(pytest.main([*(prefix+name for name in names),'-q']))
