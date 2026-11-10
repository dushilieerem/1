"""Current published metadata only; actual DB and outbound connections forbidden."""
import os,sys,json,socket
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
root=Path(__file__).resolve().parents[4];pid=int(sys.argv[1])
os.environ.update(dict(item.split('=',1) for item in Path('/proc/'+str(pid)+'/environ').read_bytes().decode().split('\0') if '=' in item));os.environ['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1';sys.path.insert(0,str(root/'backend'))
with ExitStack() as guards:
 guards.enter_context(patch('psycopg.connect',side_effect=AssertionError('No DB in metadata check')));guards.enter_context(patch.object(socket,'create_connection',side_effect=AssertionError('No network in metadata check')))
 from services.workflow_workspace.platform_data import published_view
 from services.quant_factor.research_contract import from_project
 from services.quant_data_resources import dataset
 matches=[]
 def visit(value):
  if isinstance(value,list):
   if len(value)==40 and all(isinstance(x,str) and x.endswith(('.SH','.SZ')) for x in value):matches.append(value)
   for item in value:visit(item)
  elif isinstance(value,dict):
   for item in value.values():visit(item)
 visit(json.loads((root/'institutional-workflow/runtime/verification/codex-factor-cr097-20261109/three-run-preparation.json').read_text()));assert matches
 project={'id':'cr100-readonly-plan','config':{'universe':'CSI500','researchUniverseSymbols':matches[0],'researchPlan':{'fieldRestriction':'ohlcv','developmentStart':'2025-07-01','developmentEnd':'2025-09-30','validationStart':'2026-06-22','validationEnd':'2026-09-21','rules':{'direction':'positive','icMetric':'rank_ic','minSignedIc':.005,'maxDrawdown':.5,'minObservations':60}}}}
 view=published_view();meta=dataset(2527,261,'daily_bars',view['view_id']);contract=from_project(2527,261,project,view)
 record={'read_only_metadata':True,'database_network_forbidden':True,'view_id':view['view_id'],'published':meta['published'],'catalog_version':meta['catalog_version'],'publication_version':meta['publication_version'],'field_names':[f['name'] for f in meta['fields']],'contract_fields':contract['allowed_fields'],'static_sample_count':40,'contract_hash':contract['contract_hash'],'method_identity':contract['method_identity'],'used_datasets':list(contract['data_identity']['datasets']),'no_model_market_or_business_write':True}
 Path(__file__).with_name('actual-metadata-freeze.json').write_text(json.dumps(record,ensure_ascii=False,indent=2));print(json.dumps(record,ensure_ascii=False))
