"""Version, authority, provenance and task agent regressions. All model calls stubbed."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from services.workflow_workspace.service import Workspace
from services.workflow_workspace.tasks import ResearchTasks,Conflict
from services.workflow_workspace.task_agent import TaskAgent
from services.workflow_workspace.server import create_app

def compute(base,path,body=None,**kw):
    if path=='/catalog':return {'releases':[{'version':'TEST','status':'published','symbols':list('abcdefgh'),'quality':{'start':'2024-01-01','end':'2024-12-31'}}]}
    if path=='/health':return {'capabilities':{'fields':['close'],'functions':{'delay':2},'preprocess':['none','winsor_zscore'],'limits':{}}}
    if path=='/tools/validate_expression':
        if 'future' in body['expression']:raise ValueError('禁止未来字段')
        return {'normalized':body['expression']}
    kind=path.rsplit('/',1)[-1]
    return {'kind':kind,'summary':{'ic_mean':.03,'rank_ic_mean':.04,'valid_days':100,'sharpe':1.1,'observations':100,'max_drawdown':-.1},
            'checks':[{'name':'test','status':'pass'}],'coverage':.9,'segments':[{'rank_ic_mean':.02},{'rank_ic_mean':.03}],
            'data':{'version':'TEST'},'returns':[{'date':'2024-01-02','value':.01}]}

class TaskTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.ws=Workspace(self.tmp.name,'http://127.0.0.1:18798')
        self.ws.agent=TaskAgent(self.ws,'test-no-real-key');self.tasks=ResearchTasks(self.ws)
        self.mock=patch('services.workflow_workspace.service.rpc',side_effect=compute);self.mock.start()
    def tearDown(self):
        self.ws.agent.pool.shutdown(wait=True);self.ws.pool.shutdown(wait=True);self.mock.stop();self.tmp.cleanup()
    def task(self,kind='factor',inputs=None):return self.tasks.create({'module':kind,'inputs':inputs or ({'expression':'close'} if kind=='factor' else {})})
    def run_factor(self):
        t=self.task();r=self.ws.wait(self.tasks.execute(t['id'],1)['id']);return t,r
    def finish_agent(self,a):
        end=time.monotonic()+5
        while time.monotonic()<end:
            result=self.ws.store.get('agent',a['id'])
            if result['status'] not in ('queued','running'):return result
            time.sleep(.01)
        self.fail('agent timeout')
    def test_task_versions_are_immutable(self):
        t=self.task();new=self.tasks.update(t['id'],1,{'name':'changed'})
        self.assertEqual(new['revision'],2);self.assertEqual(self.ws.store.get('task_version',t['id']+':1')['inputs']['name'],t['inputs']['name'])
        with self.assertRaises(Conflict):self.tasks.update(t['id'],1,{'name':'stale'})
    def test_same_inputs_do_not_invalidate_report(self):
        t=self.task();self.assertEqual(self.tasks.update(t['id'],1,{'expression':'close'})['revision'],1)
    def test_one_experiment_per_successful_revision(self):
        t,r=self.run_factor();again=self.tasks.execute(t['id'],1)
        self.assertEqual(r['id'],again['id']);self.assertEqual(len(self.ws.store.list('run')),1)
    def test_stale_report_cannot_submit(self):
        t,r=self.run_factor();self.tasks.update(t['id'],1,{'expression':'close/2'})
        with self.assertRaises(ValueError):self.tasks.submit(t['id'],2,r['id'],'review evidence')
        with self.assertRaises(ValueError):self.ws.submit(r['id'],'legacy cannot bypass')
    def test_pending_revision_is_frozen(self):
        t,r=self.run_factor();self.tasks.submit(t['id'],1,r['id'],'review evidence')
        with self.assertRaises(Conflict):self.tasks.update(t['id'],1,{'name':'change'})
        self.ws.decide(r['id'],'return','needs changes');self.assertEqual(self.tasks.update(t['id'],1,{'name':'change'})['revision'],2)
    def test_failed_screen_is_retained_but_not_submitted(self):
        t,r=self.run_factor();r['report']['summary']['rank_ic_mean']=.001;self.ws.store.put('run',r['id'],r)
        self.assertFalse(self.tasks.screen(r)['eligible']);self.assertEqual(len(self.tasks.assets()),1)
        with self.assertRaisesRegex(ValueError,'筛选'):self.tasks.submit(t['id'],1,r['id'],'low IC research')
    def test_wrong_direction_in_one_segment_fails_screen(self):
        _,r=self.run_factor();r['report']['segments'][1]['rank_ic_mean']=-.05
        self.assertFalse(self.tasks.screen(r)['eligible'])
    def test_nonfinite_or_missing_evidence_fails_screen(self):
        _,r=self.run_factor();r['report']['coverage']=None
        self.assertFalse(self.tasks.screen(r)['eligible'])
    def test_strategy_can_use_unreviewed_research_factor(self):
        t,r=self.run_factor();s=self.task('strategy',{'factors':[{'id':r['id'],'weight':1}]})
        sr=self.ws.wait(self.tasks.execute(s['id'],1)['id'])
        self.assertEqual(sr['status'],'completed');self.assertEqual(sr['snapshot']['components'][0]['expression'],'close')
        self.assertEqual(sr['snapshot']['components'][0]['report_sha256'],r['report_sha256'])
        self.assertEqual(self.ws.report(r['id'])['review'],'not_submitted')
    def test_research_input_cannot_supply_arbitrary_expression(self):
        t,r=self.run_factor();s=self.task('strategy')
        with self.assertRaises(ValueError):self.tasks.update(s['id'],1,{'components':[{'expression':'future'}]})
        with self.assertRaises(ValueError):self.tasks.update(s['id'],1,{'factors':[{'id':r['id'],'weight':1,'expression':'future'}]})
    def test_portfolio_resolves_fixed_strategy_report(self):
        _,r=self.run_factor();s=self.task('strategy',{'factors':[{'id':r['id'],'weight':1}]});sr=self.ws.wait(self.tasks.execute(s['id'],1)['id'])
        p=self.task('portfolio',{'strategies':[{'id':sr['id'],'weight':.8}]})
        pr=self.ws.wait(self.tasks.execute(p['id'],1)['id'])
        self.assertEqual(pr['snapshot']['components'][0]['report_sha256'],sr['report_sha256'])
    def test_weights_finite_unique_and_bounded(self):
        for v in ([{'id':'x','weight':float('nan')}],[{'id':'x','weight':1},{'id':'x','weight':1}],[{'id':'x','weight':True}],[{'id':'x','weight':-1}]):
            with self.assertRaises(ValueError):self.task('portfolio',{'strategies':v})
        with self.assertRaises(ValueError):self.task('portfolio',{'strategies':[{'id':'x','weight':.7},{'id':'y','weight':.7}]})
    def test_dates_limits_and_published_version_validated(self):
        for patch in ({'start':'2023-01-01'},{'end':'2025-01-01'},{'start':'2024-02-30'},{'data_version':'unknown'},{'horizon':21},{'groups':True}):
            with self.assertRaises(ValueError):self.task(inputs=dict(expression='close',**patch))
    def test_stage_patch_cannot_change_other_steps_or_approval(self):
        t=self.task()
        for p in ({'expression':'close'},{'review':'approved'},{'token_limit':1000000}):
            with self.assertRaises(ValueError):self.tasks.patch_for_stage(t,0,p)
    def test_fill_form_has_no_save_or_run_side_effect(self):
        def answer(messages,tools,identity):
            self.assertEqual({x['function']['name'] for x in tools},{'fill_current_step','validate_expression'})
            if len(messages)==2:return {'role':'assistant','tool_calls':[{'id':'a','function':{'name':'fill_current_step','arguments':json.dumps({'expression':'close/2'})}}]}
            return {'role':'assistant','content':'suggestion'}
        t=self.task()
        with patch.object(self.ws.agent,'_completion',side_effect=answer):
            a=self.ws.agent.start({'task_id':t['id'],'revision':1,'stage':1,'intent':'task_fill','message':'fill expression'});result=self.finish_agent(a)
        self.assertEqual(result['status'],'completed');self.assertEqual(result['form_patch']['expression'],'close/2')
        self.assertEqual(self.tasks.get(t['id'])['inputs']['expression'],'close');self.assertEqual(self.ws.store.list('run'),[])
        self.tasks.update(t['id'],1,{'name':'manual modification'})
        with self.assertRaises(Conflict):self.tasks.update(t['id'],result['task_revision'],result['form_patch'])
    def test_stage_agent_calls_real_shared_tool_and_records_evidence(self):
        def answer(messages,tools,identity):
            if len(messages)==2:return {'role':'assistant','tool_calls':[{'id':'a','function':{'name':'execute_research','arguments':'{}'}}]}
            return {'role':'assistant','content':'actual compute finished'}
        t=self.task()
        with patch.object(self.ws.agent,'_completion',side_effect=answer):
            a=self.ws.agent.start({'task_id':t['id'],'revision':1,'stage':2,'intent':'task_stage','message':'run factor test'});result=self.finish_agent(a)
        self.assertEqual(result['status'],'completed');self.assertEqual(len(result['run_ids']),1)
        r=self.ws.report(result['run_ids'][0]);self.assertEqual(r['source'],'AI');self.assertEqual(r['task_revision'],1)
        self.assertTrue(any(s['kind']=='observation' for s in result['steps']))
    def test_agent_cannot_invoke_unavailable_approval(self):
        def answer(messages,tools,identity):
            if len(messages)==2:return {'role':'assistant','tool_calls':[{'id':'escape','function':{'name':'approve','arguments':'{}'}}]}
            return {'role':'assistant','content':'not permitted'}
        t=self.task()
        with patch.object(self.ws.agent,'_completion',side_effect=answer):
            a=self.ws.agent.start({'task_id':t['id'],'revision':1,'stage':4,'intent':'task_stage','message':'review evidence'});result=self.finish_agent(a)
        self.assertEqual(self.ws.store.list('library'),[])
        self.assertTrue(any('未授权' in str(s.get('detail')) for s in result['steps']))
    def test_missing_model_key_does_not_fake_success(self):
        t=self.task();self.ws.agent.key=''
        with self.assertRaisesRegex(ValueError,'真实模型'):self.ws.agent.start({'task_id':t['id'],'revision':1,'stage':1,'intent':'task_fill','message':'fill form'})
    def test_pending_task_agent_blocks_human_edit(self):
        t=self.task();self.ws.store.put('agent','AI-test',{'id':'AI-test','status':'queued','intent':'task_stage','task_id':t['id']})
        with self.assertRaises(Conflict):self.tasks.update(t['id'],1,{'name':'manual conflict'})
        self.tasks.update(t['id'],1,{'name':'AI update'},'AI','AI-test')
    def test_bad_results_not_in_research_asset_picker(self):
        t,r=self.run_factor();r['report']['checks']=[{'status':'fail'}];self.ws.store.put('run',r['id'],r)
        self.assertEqual(self.tasks.assets(),[])
        s=self.task('strategy',{'factors':[{'id':r['id'],'weight':1}]})
        with self.assertRaises(ValueError):self.tasks.execute(s['id'],1)

class HttpTaskTest(unittest.TestCase):
    def test_conflict_status_and_no_secret_response(self):
        with tempfile.TemporaryDirectory() as tmp,patch('services.workflow_workspace.service.rpc',side_effect=compute):
            (Path(tmp)/'assets').mkdir()
            app=create_app(tmp,tmp,'http://127.0.0.1:18798',18796,'private-test-key')
            with TestClient(app,base_url='http://127.0.0.1:18796') as c:
                t=c.post('/api/v3/tasks',json={'module':'factor'}).json()
                response=c.post('/api/v3/tasks/update',json={'id':t['id'],'revision':0,'patch':{'name':'stale'}})
                self.assertEqual(response.status_code,409)
                self.assertNotIn('private-test-key',c.get('/api/v3/state').text)
                self.assertEqual(c.post('/api/v3/tasks',json={'module':'factor'},headers={'Origin':'https://evil.example'}).status_code,403)

if __name__=='__main__':unittest.main()
