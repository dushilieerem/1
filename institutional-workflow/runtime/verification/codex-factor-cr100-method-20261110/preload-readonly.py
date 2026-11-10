"""Only this product's task counts, grant and private compute inventory; no writes."""
from pathlib import Path
import sys,os,json,datetime,urllib.request
from contextlib import contextmanager
from unittest.mock import patch
import psycopg
from psycopg.rows import dict_row
root=Path(__file__).resolve().parents[4];pid=int(sys.argv[1])
values=dict(item.split('=',1) for item in Path('/proc/'+str(pid)+'/environ').read_bytes().decode().split('\0') if '=' in item)
os.environ.update(values);os.environ['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1';sys.path.insert(0,str(root/'backend'))
from services.core.db import database_url
from services.quant_factor import model_budget
@contextmanager
def readonly():
 with psycopg.connect(database_url(),row_factory=dict_row,connect_timeout=5,options='-c default_transaction_read_only=on -c statement_timeout=5000') as c:yield c
record={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bff_pid':pid,'read_only_transaction':True,'counts':{}}
with readonly() as c:
 for key,table,clause in [('f0','quant_factor_f0_runs',"status IN ('queued','running')"),('candidates','quant_factor_candidates',"status LIKE '%_running'"),('sealed','quant_factor_sealed_validations',"status IN ('queued','running')"),('agent_jobs','quant_factor_agent_jobs',"status IN ('queued','running')"),('iterations','quant_factor_iterations',"status IN ('queued','running')")]:record['counts'][key]=c.execute('SELECT COUNT(*) AS n FROM '+table+' WHERE '+clause).fetchone()['n']
 user=c.execute("SELECT id,ai_quota_daily FROM users WHERE username='test'").fetchone()
 used=c.execute("SELECT COUNT(*) n FROM ai_usage WHERE user_id=%s AND created_at>=date_trunc('day',NOW())",(user['id'],)).fetchone()['n']
 record['researcher_quota']={'daily_calls':int(user['ai_quota_daily'] or 0),'used_calls':used,'remaining_calls':max(0,int(user['ai_quota_daily'] or 0)-used)}
with patch.object(model_budget,'get_conn',readonly):record['institution_factor_budget']=model_budget.status(2527,261)
from services.quant_factor.re_client import headers
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(urllib.request.Request('http://127.0.0.1:18804/api/factor/compute-capabilities',headers=headers()),timeout=8) as r:
 cap=json.load(r);record['private_re']={'http_status':r.status,'activity':cap['activity'],'service_id':cap.get('service_id'),'method_version':cap.get('method_version')}
record['head']=__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
Path(__file__).with_name('preload-readonly.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');print(json.dumps(record,ensure_ascii=False))
