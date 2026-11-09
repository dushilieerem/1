"""Opt-in, bounded PostgreSQL checks in a unique schema of svquant_dev only.

Fixtures are synthetic. No model, backtest, public tables or existing data are used.
"""
import copy
import os
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from urllib.parse import urlparse
from unittest.mock import patch
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from services.core.db import database_url
from services.quant_factor import assets,f0,service,repo
from services.quant_factor.policy import WorkflowError,digest
from tests.test_quant_factor_assets import fixture

@unittest.skipUnless(os.environ.get('QUANT_FACTOR_PG_INTEGRATION')=='1','explicit isolated PostgreSQL opt-in required')
class IsolatedAssetPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url=database_url()
        if urlparse(cls.url).path!='/svquant_dev':raise RuntimeError('integration fixtures require the explicit development database')
        cls.schema='codex_qf_asset_test_'+uuid.uuid4().hex[:12]
        cls.uid=1_000_000_000+int(uuid.uuid4().hex[:6],16);cls.org=cls.uid+100_000_000;cls.reviewer=cls.uid+1
        with psycopg.connect(cls.url) as c:
            c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(cls.schema)))
        try:
            with cls.connection() as c:
                for statement in [
                    'CREATE TABLE detect_projects(user_id bigint,id text,name text,factor_name text,config jsonb,PRIMARY KEY(user_id,id))',
                    'CREATE TABLE quant_factor_topics(id text PRIMARY KEY,user_id bigint,org_id bigint,project_id text,view_id text,policy_version text,primary_holding_period int,max_trials int,status text,FOREIGN KEY(user_id,project_id) REFERENCES detect_projects(user_id,id))',
                    'CREATE TABLE quant_factor_candidates(id text PRIMARY KEY,user_id bigint,org_id bigint,project_id text,status text,snapshot_hash text,snapshot jsonb,evidence jsonb,archive jsonb,events jsonb,updated_at timestamptz DEFAULT now(),FOREIGN KEY(user_id,project_id) REFERENCES detect_projects(user_id,id))',
                    'CREATE TABLE quant_factor_trials(id text,topic_id text,user_id bigint,org_id bigint,project_id text,trial_no int,report_id text,outcome text,kind text,holding_period int,returned_metrics boolean)',
                    'CREATE TABLE quant_factor_sealed_validations(candidate_id text,topic_id text,user_id bigint,org_id bigint,snapshot_hash text,status text,report_id text,view_id text,result jsonb)',
                    'CREATE TABLE quant_factor_branches(id text,user_id bigint,org_id bigint,topic_id text)',
                    'CREATE TABLE quant_factor_f0_runs(id text PRIMARY KEY,user_id bigint,org_id bigint,project_id text,topic_id text,branch_id text,idempotency_key text,status text,decision jsonb,rounds int,stop_reason text,view_id text,created_at timestamptz DEFAULT now(),updated_at timestamptz DEFAULT now(),UNIQUE(user_id,org_id,topic_id,idempotency_key),FOREIGN KEY(user_id,project_id) REFERENCES detect_projects(user_id,id))',
                ]:c.execute(statement)
        except Exception:
            cls.tearDownClass();raise
    @classmethod
    def tearDownClass(cls):
        if not cls.schema.startswith('codex_qf_asset_test_'):raise RuntimeError('refuse cleanup outside owned fixture schema')
        with psycopg.connect(cls.url) as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(cls.schema)))
    @classmethod
    @contextmanager
    def connection(cls):
        with psycopg.connect(cls.url,row_factory=dict_row) as c:
            c.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(cls.schema)))
            c.execute("SET LOCAL statement_timeout='5s'")
            c.execute("SET LOCAL lock_timeout='2s'")
            yield c
    def setUp(self):
        self.row,self.facts=fixture();self.row.update(user_id=self.uid,org_id=self.org);self.row['archive']['review']['assigned_to']=self.reviewer
        with self.connection() as c:
            c.execute('TRUNCATE quant_factor_f0_runs,quant_factor_sealed_validations,quant_factor_trials,quant_factor_branches,quant_factor_candidates,quant_factor_topics,detect_projects CASCADE')
            c.execute('INSERT INTO detect_projects VALUES(%s,%s,%s,%s,%s)',(self.uid,'project',self.facts['project']['name'],'known',Jsonb(self.facts['project']['config'])))
            c.execute("INSERT INTO quant_factor_topics VALUES('topic',%s,%s,'project','view','policy-v1',1,2,'active')",(self.uid,self.org))
            self.insert_candidate(c,self.row)
            c.execute("INSERT INTO quant_factor_trials VALUES('trial','topic',%s,%s,'project',1,'qf_candidate_development','passed','research',1,true)",(self.uid,self.org))
            seal=self.facts['sealed'];c.execute('INSERT INTO quant_factor_sealed_validations VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',('candidate','topic',self.uid,self.org,self.row['snapshot_hash'],'passed','sealed_report','view',Jsonb(seal['result'])))
            c.execute("INSERT INTO quant_factor_branches VALUES('branch',%s,%s,'topic')",(self.uid,self.org))
    def insert_candidate(self,c,row):
        c.execute('INSERT INTO quant_factor_candidates(id,user_id,org_id,project_id,status,snapshot_hash,snapshot,evidence,archive,events) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(row['id'],row['user_id'],row['org_id'],row['project_id'],row['status'],row['snapshot_hash'],Jsonb(row['snapshot']),Jsonb(row['evidence']),Jsonb(row['archive']),Jsonb([])))
    def approve(self):return assets.approve(self.reviewer,self.org,'candidate','真实PG隔离事务验证',{'display_name':'隔离资产','category':'反转因子','tags':['测试']},True)
    def stored(self):
        with self.connection() as c:return c.execute("SELECT archive,events FROM quant_factor_candidates WHERE id='candidate'").fetchone()
    def test_parallel_approval_is_idempotent_in_real_transactions(self):
        barrier=threading.Barrier(2)
        def invoke(_):barrier.wait(timeout=2);return self.approve()
        with patch.object(assets,'get_conn',self.connection),ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(invoke,[1,2]))
        self.assertEqual([r['id'] for r in results],['qfa_candidate','qfa_candidate'])
        saved=self.stored();self.assertEqual(len(saved['events']),1);self.assertTrue(saved['archive']['approved'])
    def test_write_failure_rolls_back_approval_and_asset_and_event(self):
        class FailingConnection:
            def __init__(self,conn):self.conn=conn
            def execute(self,statement,*args):
                result=self.conn.execute(statement,*args)
                if str(statement).startswith('UPDATE quant_factor_candidates'):raise RuntimeError('injected after real UPDATE')
                return result
        @contextmanager
        def failing():
            with self.connection() as c:yield FailingConnection(c)
        with patch.object(assets,'get_conn',failing),self.assertRaisesRegex(RuntimeError,'injected'):self.approve()
        saved=self.stored();self.assertFalse(saved['archive'].get('approved'));self.assertNotIn('research_asset',saved['archive']);self.assertEqual(saved['events'],[])
    def test_other_computed_candidate_without_ledger_blocks_real_approval(self):
        other=copy.deepcopy(self.row);other['id']='other-candidate';other['snapshot']['plan']['hypothesis']='另一个固定测试候选';other['snapshot_hash']=digest(other['snapshot']);other['evidence']['development']['report_id']='qf_other-candidate_development'
        with self.connection() as c:self.insert_candidate(c,other)
        with patch.object(assets,'get_conn',self.connection),self.assertRaisesRegex(WorkflowError,'尚未完整落账'):self.approve()
        self.assertFalse(self.stored()['archive'].get('approved'))
    def test_start_and_approval_use_compatible_lock_order(self):
        barrier=threading.Barrier(2)
        def start():barrier.wait(timeout=2);return f0.start(self.uid,self.org,'topic','branch','start-key')
        def approve():
            barrier.wait(timeout=2)
            try:return self.approve()
            except WorkflowError as exc:self.assertIn('在途',str(exc));return {'blocked':True}
        began=time.monotonic()
        with patch.object(assets,'get_conn',self.connection),patch.object(f0,'get_conn',self.connection),patch.object(repo,'get_conn',self.connection),patch.object(service,'control_status',return_value={'paused':False}),patch.object(f0,'published_view',return_value={'view_id':'view'}),patch.object(f0.POOL,'submit'),ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(start),pool.submit(approve)];results=[f.result(timeout=6) for f in futures]
        self.assertLess(time.monotonic()-began,6);self.assertEqual(results[0]['status'],'queued')
    def test_computed_unrecorded_candidate_reserves_budget_until_trial_exists(self):
        other=copy.deepcopy(self.row);other['id']='other-candidate';other['snapshot_hash']='other';other['evidence']['development']['report_id']='qf_other-candidate_development'
        with self.connection() as c:
            self.insert_candidate(c,other)
            self.assertEqual(service._reserved_development(c,self.uid,self.org,'project'),1)
            c.execute("INSERT INTO quant_factor_trials VALUES('other-trial','topic',%s,%s,'project',2,'qf_other-candidate_development','passed','research',1,true)",(self.uid,self.org))
            self.assertEqual(service._reserved_development(c,self.uid,self.org,'project'),0)

    def test_worker_recovery_lease_allows_only_one_execution(self):
        barrier=threading.Barrier(2);calls=[]
        def once(*args):calls.append(args);time.sleep(.15)
        def invoke(_):barrier.wait(timeout=2);return service.run(self.uid,self.org,'candidate','development')
        with patch.object(service,'get_conn',self.connection),patch.object(service,'_run_once',side_effect=once),ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(invoke,[1,2]))
        self.assertEqual(len(calls),1)
