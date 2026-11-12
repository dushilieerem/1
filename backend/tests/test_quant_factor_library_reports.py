import copy,math,unittest
from unittest.mock import MagicMock,patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.errors import install_exception_handlers
from app.routers import quant_factor_workflow as routes
from services.quant_factor import library_reports as library,asset_reports,assets
from services.quant_factor.policy import digest,WorkflowError
from services.quant_factor.library_source import SourceLookupError

ROW={'id':'import-one','source_library':'主因子库','source_factor_id':'SV01_0001','factor_name':'SV01_0001','display_name':'连续下跌计数','category':'动量'}

def conn(imported=ROW,history=None,runs=None,candidate=None,sealed=None):
 c=MagicMock();c.__enter__.return_value=c
 def execute(sql,args=None):
  assert sql.lstrip().startswith('SELECT'),sql
  cursor=MagicMock()
  if 'quant_factor_imported_factors' in sql:cursor.fetchone.return_value=imported
  elif 'factor_dashboard_metrics' in sql:cursor.fetchall.return_value=history or []
  elif 'detect_runs' in sql:cursor.fetchall.return_value=runs or []
  elif 'quant_factor_candidates' in sql:cursor.fetchone.return_value=candidate
  elif 'quant_factor_sealed_validations' in sql:cursor.fetchone.return_value=sealed
  else:raise AssertionError(sql)
  return cursor
 c.execute.side_effect=execute;return c


def raw_report(start='2025-07-01'):
 return {'metrics':{'rank_ic':.03,'annual_return':.12,'unavailable':None},'error':None,
  'date_range':{'start':start,'end':'2025-09-30'},'equity_curve':[{'date':'2025-07-02','value':None,'drawdown':None},{'date':start,'value':1.02,'drawdown':-.03}],
  'benchmark_curve':[{'date':start,'value':1.0}],
  'factor_analysis':{'ic_series':[{'date':start,'value':.1,'sample_size':40}],
    'rank_ic_series':[{'date':start,'value':None,'sample_size':0}],
    'cumulative_series':[{'date':start,'layer1':1.02,'layer5':.99}],
    'quantile_metrics':[{'quantile':'Q1','turnover':.2,'excess_volatility':.03}],
    'definition':{'forward_return_days':1,'groups':5,'ic_type':'pearson','rank_ic_type':'spearman_rank','ic_unavailable_reason':None,'private_note':'HIDDEN'},
    'private_chat':'HIDDEN'},
  'meta':{'factor_source_hash':'source','data_release_id':'release','spec_hash':'spec','_token':'HIDDEN',
    'factor_price_source':'adjusted','cost_model':{'note':'真实费用口径'},'warnings':['有缺值'],
    'frozen_data_identity':{'view_id':'view-3','view_manifest_sha256':'m','daily_release':'r','daily_dataset_sha256':'d','local_path':'HIDDEN'}},
  '_svquant_verified_token':'HIDDEN','private_project':'HIDDEN'}


def asset_fixture():
 raw=raw_report();request={'factor_name':'new_factor','factor_code':'def factor(self):\n    return self.close\n','start':'2025-07-01','end':'2025-09-30','universe_snapshot':['000001.SZ'],'token':'HIDDEN'}
 snap={'request':request,'rules':{}};novelty={'gate':{'complete':True},'reference_count':331}
 dev={'result':raw,'novelty':novelty,'request':{'start':'WRONG_MUTABLE_REQUEST'},'report_id':'dev-report','run_id':'dev-run'}
 sr=raw_report('2026-06-22');sr['date_range']['end']='2026-09-21'
 sb={'intent':{'request':{**request,'start':'2026-06-22','end':'2026-09-21'}},'result':sr,'run_id':'sealed-run','confirmation':'confirmed'}
 seal={'report_id':'sealed-report','result':sb}
 gate={'passed':False,'checks':[{'name':'有效IC观测数','actual':None,'threshold':60,'passed':False,'operator':'>='}]}
 asset={'schema':assets.SCHEMA,'id':'qfa_candidate-one','org_id':9,'candidate_id':'candidate-one','snapshot_hash':digest(snap),'version':1,
  'kind':'novel_factor','display_name':'固定资产','purpose':'research_only','definition':request,'approval':{'at':'2026-11-10T01:00:00Z'},
  'development_result_hash':digest(raw),'novelty_result_hash':digest(novelty),'novelty_report':{'reference_hash':'catalog','gate':{'passed':True,'complete':True,'threshold':.7,'max_abs_correlation':.2,'compared_count':1,'expected_count':1}},
  'development_report':{'report_id':'dev-report','gate':gate},'sealed_report':{'report_id':'sealed-report','result_hash':digest(sb),'summary':{'gate':gate}}}
 asset['registration_hash']=digest(asset)
 row={'asset':asset,'snapshot_hash':digest(snap),'snapshot':snap,'evidence':{'development':dev},'private_chat':'HIDDEN'}
 return row,seal

class LibraryTests(unittest.TestCase):
 def test_all_history_combinations_and_original_units_nulls_are_preserved(self):
  history=[{'library':'主因子库','factor_name':'SV01_0001','universe':u,'period':p,'filter_limit_up':l,'filter_suspended':1,'rules_version':'yg_v1','rank_ic':2.5,'ic_mean':-1.5,'annual_return':12,'turnover':80,'q1_turnover':None,'sharpe':1.2,'ic_std':float('nan'),'computed_at':'2026-11-09T00:00:00Z'} for u in ('CSI300','CSI500') for p in ('3m','1y','3y') for l in (0,1)]
  c=conn(history=history)
  with patch.object(library,'get_conn',return_value=c):out=library.imported_reports(7,9,'import-one')
  self.assertEqual(len(out['history_summaries']),12);self.assertEqual(len({x['id'] for x in out['history_summaries']}),12)
  x=out['history_summaries'][0];self.assertEqual(x['metrics']['rank_ic'],.025);self.assertEqual(x['metrics']['ic_mean'],-.015);self.assertEqual(x['metrics']['annual_return'],.12);self.assertEqual(x['metrics']['turnover'],.8);self.assertEqual(x['metrics']['sharpe'],1.2)
  self.assertIsNone(x['metrics']['ic_std']);self.assertIsNone(x['metrics']['q1_turnover']);self.assertIsNone(x['date_range']);self.assertEqual(x['provenance']['source_metrics']['rank_ic'],2.5);self.assertEqual(x['provenance']['source_metric_units']['rank_ic'],'percent_points');self.assertIsNone(x['provenance']['factor_source_hash'])
  self.assertEqual(c.execute.call_args_list[0].args[1],('import-one',9))
 def test_no_foreign_import_or_private_source_and_readonly_role_never_queries_runs(self):
  with patch.object(library,'get_conn',return_value=conn(imported=None)) as db:
   with self.assertRaises(SourceLookupError) as e:library.imported_reports(7,99,'import-one')
   self.assertEqual(e.exception.status,404);self.assertEqual(db.return_value.execute.call_count,1)
  c=conn()
  with patch.object(library,'get_conn',return_value=c):out=library.imported_reports(7,9,'import-one',False)
  self.assertFalse(out['private_reports_allowed']);self.assertEqual(out['saved_reports'],[]);self.assertFalse(any('detect_runs' in x.args[0] for x in c.execute.call_args_list))
 def test_exact_library_id_no_override_or_conflicting_libraries_and_owner_scope(self):
  good={'id':'existing-report','factor_name':'SV01_0001','parameters':{'universe':'CSI300','start':'2020-01-01','end':'2020-03-31'},'actual_date_range':{'start':'2025-07-01','end':'2025-09-30'},'factor_source_hash':'source','has_equity_curve':True,'elapsed_sec':0,'finished_at':None}
  c=conn(runs=[good])
  with patch.object(library,'get_conn',return_value=c):out=library.imported_reports(7,9,'import-one')
  self.assertEqual([x['id'] for x in out['saved_reports']],['existing-report']);x=out['saved_reports'][0]
  self.assertEqual(x['actual_date_range']['start'],'2025-07-01');self.assertIsNone(x['finished_at']);self.assertEqual(x['elapsed_seconds'],0);self.assertEqual(x['version']['factor_source_hash'],'source');self.assertEqual(x['report_url'],'/quant/factor/report/existing-report');self.assertNotIn('result',x)
  sql,args=c.execute.call_args.args;self.assertIn('user_id=%s',sql);self.assertEqual(args[:2],(7,'SV01_0001'));self.assertEqual(args[-1],51)
  self.assertNotIn('SELECT *',sql);self.assertNotIn(',result,',sql);self.assertIn('jsonb_array_length',sql);self.assertIn("COALESCE(request->>'factor_code','')=''",sql)
  where=sql.split(' WHERE ')[1];self.assertTrue(where.index('library_name')<where.index('LIMIT'));self.assertIn("COALESCE(request->>'factor_name','')",where)
  # Both optional aliases are constrained, not merely one OR match.
  self.assertEqual(where.count("IN ('null'::jsonb"),2)
 def test_manual_cursor_is_bounded_scoped_and_does_not_load_curves(self):
  rows=[{'id':'r'+str(i),'factor_name':'SV01_0001','finished_at':'2026-11-09T01:00:00+00:00'} for i in range(51)]
  c=conn(runs=rows,history=[{'rules_version':'yg_v1'}]*101)
  with patch.object(library,'get_conn',return_value=c):out=library.imported_reports(7,9,'import-one')
  self.assertEqual(len(out['saved_reports']),50);self.assertTrue(out['saved_reports_page']['has_more']);self.assertEqual(len(out['history_summaries']),100);self.assertTrue(out['history_page']['has_more'])
  cursor=out['saved_reports_page']['next_cursor']
  c=conn(runs=[])
  with patch.object(library,'get_conn',return_value=c):last=library.imported_reports(7,9,'import-one',True,cursor)
  self.assertFalse(last['saved_reports_page']['has_more']);sql,args=c.execute.call_args.args;self.assertIn("COALESCE(finished_at,'-infinity'",sql);self.assertEqual(args[-3:-1],('2026-11-09T01:00:00+00:00','r49'))
  for uid,org,fid in [(8,9,'import-one'),(7,10,'import-one'),(7,9,'import-two')]:
   with self.subTest(uid=uid,org=org,fid=fid),patch.object(library,'get_conn') as db:
    with self.assertRaises(SourceLookupError) as e:library.imported_reports(uid,org,fid,True,cursor)
    self.assertEqual(e.exception.status,400);db.assert_not_called()
 def test_failure_and_unavailable_are_not_empty_success(self):
  with patch.object(library,'get_conn',side_effect=RuntimeError('private secret')):
   with self.assertRaises(SourceLookupError) as e:library.imported_reports(7,9,'import-one')
   self.assertEqual(e.exception.status,503);self.assertNotIn('secret',str(e.exception))
  unknown=library.summary({'rules_version':'unrecognized','rank_ic':2.5});self.assertIsNone(unknown['metrics']['rank_ic']);self.assertEqual(unknown['provenance']['source_metrics']['rank_ic'],2.5);self.assertEqual(unknown['provenance']['source_metric_units']['rank_ic'],'unknown')
  invalid=library.summary({'rules_version':'yg_v1','rank_ic':125,'ic_mean':-101});self.assertIsNone(invalid['metrics']['rank_ic']);self.assertIsNone(invalid['metrics']['ic_mean']);self.assertEqual(invalid['provenance']['source_metrics']['rank_ic'],125);self.assertIn('超出有效范围',invalid['calculation_note'])
  x=library.summary({'rules_version':'yg_v1','error':'原计算失败','rank_ic':None});self.assertEqual(x['status'],'failed');self.assertEqual(x['calculation_note'],'原计算失败');self.assertIsNone(x['metrics']['rank_ic'])

class AssetTests(unittest.TestCase):
 def read(self,row,seal,phase='development'):
  with patch.object(asset_reports,'get_conn',return_value=conn(candidate=row,sealed=seal)) as db:
   out=assets.full_report(777,9,'qfa_candidate-one',phase)
  self.assertEqual(db.return_value.execute.call_args_list[0].args[1],(9,'qfa_candidate-one'));return out
 def test_member_gets_authorized_complete_frozen_projection_and_no_private_project(self):
  row,seal=asset_fixture();out=self.read(row,seal)
  self.assertTrue(out['readonly']);self.assertIsNone(out['run']['projectId']);self.assertEqual(out['run']['request']['start'],'2025-07-01');self.assertEqual(out['run']['result']['equity_curve'],row['evidence']['development']['result']['equity_curve']);self.assertEqual(out['run']['result']['factor_analysis']['ic_series'][0]['sample_size'],40)
  self.assertEqual(out['run']['result']['factor_analysis']['definition']['ic_type'],'pearson');self.assertEqual(out['run']['result']['factor_analysis']['definition']['groups'],5);self.assertEqual(out['run']['result']['factor_analysis']['quantile_metrics'][0]['excess_volatility'],.03)
  self.assertEqual(out['run']['result']['meta']['cost_model']['note'],'真实费用口径');self.assertNotIn('HIDDEN',str(out));self.assertIsNone(out['run']['finishedAt']);self.assertFalse(out['gate']['passed']);self.assertIsNone(out['gate']['checks'][0]['actual']);self.assertEqual(out['provenance']['source_result_hash'],row['asset']['development_result_hash']);self.assertEqual(out['provenance']['request_source'],'registered_definition');self.assertEqual(out['novelty']['status'],'passed');self.assertEqual(out['novelty']['gate']['threshold'],.7)
 def test_sealed_uses_hashed_intent_not_development_period_and_keeps_real_series(self):
  row,seal=asset_fixture();out=self.read(row,seal,'sealed')
  self.assertEqual(out['run']['request']['start'],'2026-06-22');self.assertEqual(out['run']['request']['end'],'2026-09-21');self.assertEqual(out['run']['result']['date_range']['start'],'2026-06-22');self.assertEqual(out['provenance']['request_source'],'sealed_intent');self.assertEqual(out['report_id'],'sealed-report')
 def test_missing_org_and_registration_source_or_report_tampering_rejected(self):
  with patch.object(asset_reports,'get_conn',return_value=conn(candidate=None)):
   with self.assertRaises(KeyError):assets.full_report(7,99,'qfa_candidate-one','development')
  for field in ('registration','snapshot','development','novelty','sealed','sealed_id'):
   row,seal=asset_fixture()
   if field=='registration':row['asset']['display_name']='changed'
   elif field=='snapshot':row['snapshot']['request']['start']='changed'
   elif field=='development':row['evidence']['development']['result']['metrics']['rank_ic']=.99
   elif field=='novelty':row['evidence']['development']['novelty']['reference_count']=1
   elif field=='sealed':seal['result']['result']['equity_curve']=[]
   else:seal['report_id']='another-report'
   with self.subTest(field=field),self.assertRaises(WorkflowError):self.read(row,seal)
 def test_projection_does_not_mutate_source_and_does_not_reorder_or_fill_missing(self):
  raw=raw_report();before=copy.deepcopy(raw);out=asset_reports.result_projection(raw)
  self.assertEqual(raw,before);self.assertEqual(out['equity_curve'],raw['equity_curve']);self.assertIsNone(out['factor_analysis']['rank_ic_series'][0]['value']);self.assertNotIn('private_chat',out['factor_analysis']);self.assertNotIn('_svquant_verified_token',out)
  raw['factor_analysis'].update(cumulative_series=None,quantile_metrics=None,industry_equity_curves=None,industry_group_equity_curves=None,ic_horizons=None,ic_series=None,rank_ic_series=None);asset_reports.result_projection(raw)

class RouteTests(unittest.TestCase):
 def app(self,ctx=None):
  app=FastAPI();app.include_router(routes.router);install_exception_handlers(app)
  if ctx is not None:app.dependency_overrides[routes.require_quant_user]=lambda:ctx
  return app
 def test_actual_routes_read_role_identity_and_phase_validation(self):
  ctx={'user':{'id':7},'org':{'id':9},'can_write':False}
  with TestClient(self.app(ctx)) as client,patch.object(routes,'_quant_uid',return_value=7),patch.object(library,'imported_reports',return_value={'history_summaries':[]}) as imports,patch.object(assets,'full_report',return_value={'readonly':True}) as asset:
   self.assertEqual(client.get('/api/inst/quant/factor-workflow/imports/i/reports').status_code,200);self.assertEqual(imports.call_args.args,(7,9,'i',False,None,50))
   self.assertEqual(client.get('/api/inst/quant/factor-workflow/assets/a/reports/sealed').status_code,200);self.assertEqual(asset.call_args.args,(7,9,'a','sealed'))
   self.assertEqual(client.get('/api/inst/quant/factor-workflow/assets/a/reports/private').status_code,400)
 def test_no_login_denied_and_missing_changed_unavailable_errors_distinct(self):
  with TestClient(self.app()) as client,patch.object(library,'imported_reports') as read:
   self.assertIn(client.get('/api/inst/quant/factor-workflow/imports/i/reports').status_code,(401,403));read.assert_not_called()
  ctx={'user':{'id':7},'org':{'id':9},'can_write':True}
  with TestClient(self.app(ctx)) as client,patch.object(routes,'_quant_uid',return_value=7):
   with patch.object(assets,'full_report',side_effect=KeyError('a')):self.assertEqual(client.get('/api/inst/quant/factor-workflow/assets/a/reports/development').status_code,404)
   with patch.object(assets,'full_report',side_effect=WorkflowError('登记快照已改变')):self.assertEqual(client.get('/api/inst/quant/factor-workflow/assets/a/reports/development').status_code,409)
   with patch.object(library,'imported_reports',side_effect=SourceLookupError(503,'reports_unavailable','报告暂不可读')):
    response=client.get('/api/inst/quant/factor-workflow/imports/i/reports');self.assertEqual(response.status_code,503);self.assertEqual(response.json(),{'error':'报告暂不可读','code':'reports_unavailable'})
