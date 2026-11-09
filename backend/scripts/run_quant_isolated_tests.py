"""Run quant unit/ASGI tests without any PostgreSQL connection or bootstrap.

Usage from backend: python scripts/run_quant_isolated_tests.py tests/test_quant_factor_cr097_flow.py
Real PG verification uses its separate explicit temporary-schema program, never this entry.
"""
import os,sys,socket
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
os.environ['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1'
sys.path.insert(0,str(ROOT));os.chdir(ROOT)
paths=sys.argv[1:]
if not paths:raise SystemExit('Pass explicit isolated test file paths; no implicit full suite.')
for value in paths:
 path=(ROOT/value).resolve()
 if path.parent!=ROOT/'tests' or path.suffix!='.py' or 'pg' in path.name.lower() or not path.is_file():raise SystemExit('Only explicit non-PG backend/tests/*.py files are allowed')
import psycopg
from services.core import db

def forbidden(*args,**kwargs):raise AssertionError('ISOLATED QUANT TEST: real PostgreSQL connections forbidden; use explicit temporary-schema PG verification instead')

original_connect=socket.socket.connect
original_connect_ex=socket.socket.connect_ex
original_send=socket.socket.send
original_sendall=socket.socket.sendall
original_sendto=socket.socket.sendto

def network_forbidden(*args,**kwargs):raise AssertionError('ISOLATED QUANT TEST: external network/HTTP forbidden; patch the exact service dependency')
def connect(sock,*args,**kwargs):
 if sock.family in (socket.AF_INET,socket.AF_INET6):return network_forbidden()
 return original_connect(sock,*args,**kwargs)
def connect_ex(sock,*args,**kwargs):
 if sock.family in (socket.AF_INET,socket.AF_INET6):return network_forbidden()
 return original_connect_ex(sock,*args,**kwargs)
def send(sock,*args,**kwargs):
 if sock.family in (socket.AF_INET,socket.AF_INET6):return network_forbidden()
 return original_send(sock,*args,**kwargs)
def sendall(sock,*args,**kwargs):
 if sock.family in (socket.AF_INET,socket.AF_INET6):return network_forbidden()
 return original_sendall(sock,*args,**kwargs)
def sendto(sock,*args,**kwargs):
 if sock.family in (socket.AF_INET,socket.AF_INET6):return network_forbidden()
 return original_sendto(sock,*args,**kwargs)

with patch.object(psycopg,'connect',side_effect=forbidden),patch.object(db,'_borrow_conn',side_effect=forbidden),patch.object(socket.socket,'connect',connect),patch.object(socket.socket,'connect_ex',connect_ex),patch.object(socket.socket,'send',send),patch.object(socket.socket,'sendall',sendall),patch.object(socket.socket,'sendto',sendto),patch.object(socket,'create_connection',side_effect=network_forbidden),patch.object(socket,'getaddrinfo',side_effect=network_forbidden):
 import pytest
 raise SystemExit(pytest.main([*paths,'-q']))
