"""Isolated product tests with fake compute/model; never charge a provider."""
import json
import tempfile
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from services.workflow_workspace.service import Workspace
from services.workflow_workspace.agent import Agent
from services.workflow_workspace.store import Store
from services.workflow_workspace.server import create_app

def compute_reply(base,path,body=None,**kwargs):
    if path=='/tools/validate_expression':
        if body['expression']=='bad':raise ValueError('bad expression')
        return {'normalized':body['expression']}
    if path=='/catalog':return {'releases':[{'version':'TEST','status':'published','symbols':['a','b','c','d'],'quality':{'start':'2024-01-01','end':'2024-12-31'}}]}
    if path=='/health':return {'capabilities':{'fields':['close'],'functions':{'delay':2},'preprocess':['none']}}
    return {'kind':path.split('/')[-1],'summary':{'ic_mean':.05},'checks':[{'status':'pass'}],'data':{'version':'TEST'},'returns':[{'date':'2024-01-02','value':.01}]}

class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.ws=Workspace(self.temp.name,'http://127.0.0.1:8798');self.ws.agent=Agent(self.ws,'test-key-not-real')
        self.mock=patch('services.workflow_workspace.service.rpc',side_effect=compute_reply);self.mock.start()
    def tearDown(self):
        self.ws.agent.pool.shutdown(wait=True);self.ws.pool.shutdown(wait=True);self.mock.stop();self.temp.cleanup()
    def factor(self,source='human'):
        f=self.ws.save_factor({'name':'Test','expression':'close'},source)
        return self.ws.wait(self.ws.run('factor',{'factor_id':f['id'],'data_version':'TEST','start':'2024-01-01','end':'2024-12-31'},source)['id'])
    def test_shared_human_and_ai_tools(self):
        a=self.factor('human');b=self.factor('AI')
        self.assertEqual(a['report'],b['report']);self.assertEqual(a['report_sha256'],b['report_sha256'])
        self.assertNotEqual(a['source'],b['source'])
    def test_definition_and_experiment_snapshot(self):
        a=self.factor();original=self.ws.report(a['id'])['snapshot']
        self.ws.save_factor({'name':'Other','expression':'close/2','parent_id':original['factor_id']})
        self.assertEqual(self.ws.report(a['id'])['snapshot'],original)
    def test_ai_cannot_approve(self):
        a=self.factor();self.ws.submit(a['id'],'test evidence','AI')
        with self.assertRaisesRegex(ValueError,'AI'):self.ws.decide(a['id'],'approve','test evidence','AI')
        self.assertEqual(len(self.ws.store.list('library')),0)
    def test_approval_registers_once(self):
        a=self.factor();self.ws.submit(a['id'],'test evidence');self.ws.decide(a['id'],'approve','research only')
        with self.assertRaises(ValueError):self.ws.decide(a['id'],'approve','research only')
        assets=self.ws.store.list('library');self.assertEqual(len(assets),1);self.assertEqual(assets[0]['purpose'],'research_only')
    def test_strategy_uses_frozen_library(self):
        a=self.factor();self.ws.submit(a['id'],'test evidence');job=self.ws.decide(a['id'],'approve','research only')
        b=self.ws.wait(self.ws.run('strategy',{'factors':[{'id':job['library_id'],'weight':1}],'components':[{'expression':'untrusted'}]})['id'])
        self.assertEqual(b['snapshot']['components'][0]['expression'],'close')
    def test_missing_library_rejected(self):
        with self.assertRaises(ValueError):self.ws.run('strategy',{'factors':[{'id':'absent'}]})
    def test_hard_failure_cannot_be_submitted(self):
        a=self.factor();a['report']['checks']=[{'status':'fail'}];self.ws.store.put('run',a['id'],a)
        with self.assertRaisesRegex(ValueError,'硬检查'):self.ws.submit(a['id'],'test evidence')
    def test_returned_result_can_be_resubmitted(self):
        a=self.factor();self.ws.submit(a['id'],'test evidence');self.ws.decide(a['id'],'return','need evidence');self.ws.submit(a['id'],'new evidence')
        self.assertEqual(self.ws.report(a['id'])['review'],'pending')
    def test_restart_preserves_evidence_and_interrupts_jobs(self):
        a=self.factor();self.ws.store.put('run','RUN-pending',{'id':'RUN-pending','status':'running'})
        s=Store(self.temp.name)
        self.assertEqual(s.get('run','RUN-pending')['status'],'interrupted');self.assertEqual(s.get('run',a['id'])['report_sha256'],a['report_sha256'])
    def test_missing_key_has_no_fake_ai_fallback(self):
        self.ws.agent.key=''
        with self.assertRaisesRegex(ValueError,'真实模型'):self.ws.agent.start({'message':'test job'})
        self.assertEqual(self.ws.store.list('agent'),[])
    def test_bounded_real_tools_with_fake_model(self):
        def answer(messages,tools,identity):
            if len(messages)==2:return {'role':'assistant','content':None,'tool_calls':[{'id':'call-1','type':'function','function':{'name':'save_factor','arguments':json.dumps({'name':'model test','expression':'close','reason':'test only'})}}]}
            return {'role':'assistant','content':'Definition saved; no performance claims.'}
        with patch.object(self.ws.agent,'_completion',side_effect=answer):
            job=self.ws.agent.start({'message':'create a factor definition only'})
            end=time.monotonic()+3
            while time.monotonic()<end:
                result=self.ws.store.get('agent',job['id'])
                if result['status'] not in ('running','queued'):break
                time.sleep(.02)
        self.assertEqual(result['status'],'completed');self.assertEqual(self.ws.store.list('factor')[0]['source'],'AI');self.assertEqual(self.ws.store.list('library'),[])
    def test_form_fill_is_draft_only_and_tools_restricted(self):
        def answer(messages,tools,identity):
            self.assertEqual({t['function']['name'] for t in tools},{'fill_form','validate_expression'})
            if len(messages)==2:return {'role':'assistant','content':None,'tool_calls':[{'id':'fill','type':'function','function':{'name':'fill_form','arguments':json.dumps({'expression':'close','name':'AI draft'})}}]}
            return {'role':'assistant','content':'Draft only'}
        with patch.object(self.ws.agent,'_completion',side_effect=answer):
            job=self.ws.agent.start({'message':'fill this form','module':'factor','stage':'design','intent':'fill_form','form':{'expression':''}})
            self.ws.agent.pool.shutdown(wait=True)
        result=self.ws.store.get('agent',job['id'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['form_patch']['expression'],'close')
        for kind in ('factor','run','library'):self.assertEqual(self.ws.store.list(kind),[])
    def test_form_patch_rejects_other_stage_and_authority_fields(self):
        from services.workflow_workspace.agent import validate_form_patch
        for patch in ({'review':'approved'},{'expression':'close'},{'horizon':True},{'groups':0}):
            with self.assertRaises(ValueError):validate_form_patch('factor','test',patch)
        with self.assertRaises(ValueError):validate_form_patch('strategy','rules',{'cost_bps':float('nan')})
        with self.assertRaises(ValueError):self.ws.agent.start({'message':'fill this form','module':'review','stage':'decision','intent':'fill_form'})
    def test_form_model_cannot_call_save_or_run(self):
        def answer(messages,tools,identity):
            if len(messages)==2:return {'role':'assistant','content':None,'tool_calls':[{'id':'escape','type':'function','function':{'name':'save_factor','arguments':json.dumps({'name':'bad','expression':'close'})}}]}
            return {'role':'assistant','content':'Done'}
        with patch.object(self.ws.agent,'_completion',side_effect=answer):
            job=self.ws.agent.start({'message':'fill this form','module':'factor','stage':'design','intent':'fill_form'})
            self.ws.agent.pool.shutdown(wait=True)
        result=self.ws.store.get('agent',job['id'])
        self.assertEqual(result['form_patch'],{})
        self.assertEqual(self.ws.store.list('factor'),[])
        self.assertIn('未授权',str(result['steps']))
    def test_stage_review_is_read_only(self):
        def answer(messages,tools,identity):
            self.assertEqual([t['function']['name'] for t in tools],['read_report'])
            self.assertIn('current_form',messages[1]['content'])
            return {'role':'assistant','content':'No evidence supplied'}
        with patch.object(self.ws.agent,'_completion',side_effect=answer):
            job=self.ws.agent.start({'module':'factor','intent':'stage','stage':'results','form':{'run_ids':[]},'message':'review current result'})
            self.ws.agent.pool.shutdown(wait=True)
        self.assertEqual(self.ws.store.get('agent',job['id'])['status'],'completed')
        self.assertEqual(self.ws.store.list('run'),[])
    def test_budget_before_provider_call(self):
        s=self.ws.store.get('settings','current');s['token_limit']=1;self.ws.store.put('settings','current',s)
        self.ws.store.put('agent','AI-test',{'id':'AI-test','status':'running'})
        with patch('services.workflow_workspace.agent.request.build_opener') as net:
            with self.assertRaisesRegex(ValueError,'额度'):self.ws.agent._completion([],[],'AI-test')
            net.assert_not_called()
    def test_method_snapshot(self):
        with patch.object(self.ws.agent.pool,'submit'):
            visible_method=self.ws.state()['method']
            a=self.ws.agent.start({'message':'check actual research'});self.assertEqual(a['method'],visible_method)
            self.ws.save_method({'prompt':'New method, require documented evidence.'})
        self.assertEqual(a['method']['version'],1);self.assertEqual(self.ws.store.get('method','current')['version'],2)
    def test_agent_receives_diagnostics_and_metric_labels(self):
        a=self.factor();a['report'].update(quantiles=[{'group':'Q1','mean_forward_return':.01}],labels={'quantiles':'diagnostic only'},limitations=['selected pool'])
        evidence=Agent.summary(a)
        self.assertEqual(evidence['quantiles'],a['report']['quantiles']);self.assertEqual(evidence['labels'],a['report']['labels'])
    def test_budget_stays_within_existing_authorization(self):
        self.ws.agent.configure({'token_limit':200000})
        with self.assertRaises(ValueError):self.ws.agent.configure({'token_limit':200001})
    def test_cancel_discards_late_compute_result(self):
        started=threading.Event();release=threading.Event()
        def delayed(base,path,body=None,**kwargs):
            if path=='/tools/factor':started.set();release.wait(3)
            return compute_reply(base,path,body,**kwargs)
        with patch('services.workflow_workspace.service.rpc',side_effect=delayed):
            f=self.ws.save_factor({'name':'cancel-test','expression':'close'})
            job=self.ws.run('factor',{'factor_id':f['id']})
            try:
                self.assertTrue(started.wait(2));self.ws.cancel(job['id'])
            finally:release.set()
            self.ws.pool.shutdown(wait=True)
        result=self.ws.report(job['id']);self.assertEqual(result['status'],'cancelled');self.assertNotIn('report',result)
    def test_compute_error_preserves_failed_run(self):
        f=self.ws.save_factor({'name':'failure-test','expression':'close'})
        with patch('services.workflow_workspace.service.rpc',side_effect=ValueError('real compute unavailable')):
            job=self.ws.wait(self.ws.run('factor',{'factor_id':f['id']})['id'])
        self.assertEqual(job['status'],'failed');self.assertNotIn('report',job)
        self.assertEqual(self.ws.store.list('library'),[])
    def test_factor_agent_cannot_bypass_module_tool_scope(self):
        def reply(messages,tools,identity):
            if len(messages)==2:return {'role':'assistant','content':None,'tool_calls':[{'id':'call-1','type':'function','function':{'name':'run_strategy','arguments':'{}'}}]}
            return {'role':'assistant','content':'Scope denied.'}
        with patch.object(self.ws.agent,'_completion',side_effect=reply),patch.object(self.ws,'run') as run:
            job=self.ws.agent.start({'module':'factor','message':'test denied tool'})
            self.ws.agent.pool.shutdown(wait=True)
            run.assert_not_called()
        result=self.ws.store.get('agent',job['id'])
        self.assertIn('未授权',result['steps'][1]['detail']['error'])
    def test_live_trace_visible_before_tool_returns(self):
        entered=threading.Event();release=threading.Event()
        def answer(messages,tools,identity):
            if len(messages)==2:return {'role':'assistant','reasoning_content':'private reasoning must not be logged','content':None,'tool_calls':[{'id':'v1','function':{'name':'validate_expression','arguments':'{"expression":"close"}'}}]}
            return {'role':'assistant','content':'Validated only'}
        def validate(body):entered.set();release.wait(3);return {'normalized':body['expression']}
        with patch.object(self.ws.agent,'_completion',side_effect=answer),patch.object(self.ws,'validate',side_effect=validate):
            job=self.ws.agent.start({'module':'factor','intent':'stage','stage':'design','message':'validate this expression','form':{'expression':'close','research_id':'research-1'}})
            try:
                self.assertTrue(entered.wait(2))
                live=self.ws.store.get('agent',job['id'])
                self.assertEqual(live['steps'][-1]['status'],'running')
                self.assertEqual(live['steps'][-1]['detail'],{'expression':'close'})
                self.assertEqual(live['steps'][-1]['call_id'],'v1')
                self.assertEqual(live['form']['research_id'],'research-1')
                self.assertNotIn('private reasoning',json.dumps(live))
            finally:release.set()
            self.ws.agent.pool.shutdown(wait=True)
        result=self.ws.store.get('agent',job['id'])
        tool=next(e for e in result['steps'] if e['kind']=='tool')
        obs=next(e for e in result['steps'] if e['kind']=='observation')
        self.assertEqual(tool['status'],'completed');self.assertEqual(tool['call_id'],obs['call_id'])
        self.assertGreaterEqual(tool['duration_ms'],0)
        self.assertEqual([e['seq'] for e in result['steps']],list(range(1,len(result['steps'])+1)))
    def test_trace_retains_failure_then_success(self):
        responses=[{'role':'assistant','tool_calls':[{'id':'bad','function':{'name':'validate_expression','arguments':'{"expression":"bad"}'}}]}, {'role':'assistant','tool_calls':[{'id':'fixed','function':{'name':'validate_expression','arguments':'{"expression":"close"}'}}]}, {'role':'assistant','content':'Repaired'}]
        with patch.object(self.ws.agent,'_completion',side_effect=responses):
            job=self.ws.agent.start({'module':'factor','intent':'stage','stage':'design','message':'repair expression'})
            self.ws.agent.pool.shutdown(wait=True)
        result=self.ws.store.get('agent',job['id'])
        calls=[e for e in result['steps'] if e['kind']=='tool']
        self.assertEqual([x['status'] for x in calls],['failed','completed'])
        self.assertEqual([x['call_id'] for x in calls],['bad','fixed'])
        self.assertEqual(result['status'],'completed')
    def test_cancel_during_model_preserves_control_and_no_new_tool(self):
        entered=threading.Event();release=threading.Event()
        def answer(*args):
            entered.set();release.wait(3)
            return {'role':'assistant','tool_calls':[{'id':'late','function':{'name':'save_factor','arguments':'{"name":"late","expression":"close"}'}}]}
        with patch.object(self.ws.agent,'_completion',side_effect=answer):
            job=self.ws.agent.start({'message':'save factor after model'})
            try:
                self.assertTrue(entered.wait(2));self.ws.agent.cancel(job['id'])
            finally:release.set()
            self.ws.agent.pool.shutdown(wait=True)
        result=self.ws.store.get('agent',job['id'])
        self.assertEqual(result['status'],'cancelled');self.assertEqual(self.ws.store.list('factor'),[])
        self.assertTrue(any(e['kind']=='control' for e in result['steps']))
        self.assertFalse(any(e.get('status')=='running' for e in result['steps']))
    def test_model_failure_closes_running_trace(self):
        with patch.object(self.ws.agent,'_completion',side_effect=ValueError('provider unavailable')):
            job=self.ws.agent.start({'message':'test model failure'})
            self.ws.agent.pool.shutdown(wait=True)
        result=self.ws.store.get('agent',job['id'])
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['steps'][0]['status'],'failed')
        self.assertIn('provider unavailable',result['steps'][0]['error'])
    def test_usage_is_recorded_on_job_from_provider_response(self):
        from unittest.mock import MagicMock
        self.ws.store.put('agent','AI-usage',{'id':'AI-usage','status':'running','steps':[]})
        response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps({'choices':[{'message':{'role':'assistant','content':'ok'}}],'usage':{'total_tokens':123}}).encode()
        opener=MagicMock();opener.open.return_value=response
        with patch('services.workflow_workspace.agent.request.build_opener',return_value=opener):
            self.ws.agent._completion([],[],'AI-usage')
        self.assertEqual(self.ws.store.get('agent','AI-usage')['usage'],{'calls':1,'tokens':123,'uncertain':0})
    def test_http_same_origin_guard(self):
        with tempfile.TemporaryDirectory() as d:
            web=Path(d)/'web';(web/'assets').mkdir(parents=True);(web/'index.html').write_text('test')
            with TestClient(create_app(Path(d)/'state',web,'http://127.0.0.1:8798',8796),base_url='http://127.0.0.1:8796') as c:
                self.assertEqual(c.get('/api/state').status_code,200)
                self.assertEqual(c.post('/api/factors',json={'name':'x','expression':'close'},headers={'Origin':'https://evil.example'}).status_code,403)
                self.assertEqual(c.get('/api/state',headers={'Host':'evil.example'}).status_code,403)
                self.assertNotIn('test-key-not-real',c.get('/api/state').text)

if __name__=='__main__':unittest.main()
