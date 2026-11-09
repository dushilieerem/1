"""Bounded opt-in requests persistence checks in an owned schema; no data handoff."""
import os,unittest,uuid
from urllib.parse import urlparse
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from services.core.db import database_url
from services import quant_data_resources as svc

@unittest.skipUnless(os.environ.get('QUANT_DATA_PG_INTEGRATION')=='1','explicit isolated PG opt-in required')
class RequestPersistenceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.url=database_url()
  if urlparse(cls.url).path!='/svquant_dev':raise RuntimeError('explicit development database required')
  cls.schema='codex_qd_request_test_'+uuid.uuid4().hex[:12];cls.uid=1_300_000_000+int(uuid.uuid4().hex[:6],16);cls.org=cls.uid+1
  with psycopg.connect(cls.url) as c:c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(cls.schema)))
  with cls.connection() as c:c.execute("CREATE TABLE quant_data_requests(id text PRIMARY KEY,user_id bigint,org_id bigint,title text,purpose text,period text,frequency text,fields text,related_type text,related_id text,status text,note text,created_at timestamptz DEFAULT now())")
 @classmethod
 @contextmanager
 def connection(cls):
  with psycopg.connect(cls.url,row_factory=dict_row) as c:
   c.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(cls.schema)));c.execute("SET LOCAL statement_timeout='5s'");c.execute("SET LOCAL lock_timeout='2s'");yield c
 @classmethod
 def tearDownClass(cls):
  if not cls.schema.startswith('codex_qd_request_test_'):raise RuntimeError('refuse cleanup outside owned schema')
  with psycopg.connect(cls.url) as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(cls.schema)))
 def setUp(self):self.payload={'request_id':str(uuid.uuid4()),'title':'隔离测试需求，不转发','purpose':'因子研究','period':'2026-01','frequency':'日频','fields':'fixture_field'}
 def submit(self,uid=None,org=None,payload=None):return svc.submit_request(uid or self.uid,org or self.org,payload or self.payload)
 def test_committed_server_result_survives_lost_response_then_replay(self):
  with patch.object(svc,'get_conn',self.connection):
   try:
    first=self.submit();raise ConnectionResetError('simulate response lost after actual service transaction commit')
   except ConnectionResetError:pass
   restored=self.submit()
  self.assertEqual(first['id'],restored['id']);self.assertEqual(first['created_at'],restored['created_at'])
  with self.connection() as c:self.assertEqual(c.execute('SELECT COUNT(*) n FROM quant_data_requests WHERE id=%s',(first['id'],)).fetchone()['n'],1)
 def test_changed_body_cannot_overwrite_original(self):
  with patch.object(svc,'get_conn',self.connection):
   first=self.submit()
   with self.assertRaisesRegex(ValueError,'正文已改变'):self.submit(payload={**self.payload,'title':'changed'})
   self.assertEqual(self.submit()['title'],first['title'])
 def test_same_id_different_user_or_org_cannot_read_original(self):
  with patch.object(svc,'get_conn',self.connection):
   self.submit()
   for uid,org in [(self.uid+2,self.org),(self.uid,self.org+2)]:
    with self.assertRaisesRegex(ValueError,'身份不可用'):self.submit(uid,org)
 def test_parallel_same_identity_is_one_persisted_request(self):
  with patch.object(svc,'get_conn',self.connection),ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.submit(),range(2)))
  self.assertEqual(results[0]['id'],results[1]['id'])
  with self.connection() as c:self.assertEqual(c.execute('SELECT COUNT(*) n FROM quant_data_requests WHERE id=%s',(self.payload['request_id'],)).fetchone()['n'],1)
