"""Bounded read-only counts and existing researcher quota, no bootstrap/import of app."""
from pathlib import Path
import sys,json,datetime,os
import psycopg
from psycopg.rows import dict_row
pid=int(sys.argv[1]);root=Path(__file__).resolve().parents[4]
values={}
for item in Path('/proc/'+str(pid)+'/environ').read_bytes().split(b'\0'):
 if b'=' in item:
  k,v=item.split(b'=',1);values[k.decode()]=v.decode()
os.environ.update(values);sys.path.insert(0,str(root/'backend'))
from services.core.db import database_url
url=database_url();assert url,'original configured DB unavailable'
out={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bff_pid':pid,'read_only_transaction':True,'counts':{}}
with psycopg.connect(url,row_factory=dict_row,options='-c default_transaction_read_only=on') as c:
 c.execute("SET LOCAL statement_timeout='5s'")
 for label,table,clause in [('f0','quant_factor_f0_runs',"status IN ('queued','running')"),('candidates','quant_factor_candidates',"status LIKE '%_running'"),('sealed','quant_factor_sealed_validations',"status IN ('queued','running')"),('agent_jobs','quant_factor_agent_jobs',"status IN ('queued','running')"),('iterations','quant_factor_iterations',"status IN ('queued','running')")]:out['counts'][label]=c.execute('SELECT COUNT(*) AS n FROM '+table+' WHERE '+clause).fetchone()['n']
 user=c.execute("SELECT id,ai_quota_daily FROM users WHERE username='test'").fetchone();assert user
 used=c.execute("SELECT COUNT(*) n FROM ai_usage WHERE user_id=%s AND created_at>=date_trunc('day',NOW())",(user['id'],)).fetchone()['n']
 out['researcher_quota']={'daily_calls':int(user['ai_quota_daily'] or 0),'used_calls':used,'remaining_calls':max(0,int(user['ai_quota_daily'] or 0)-used)}
 tokens=c.execute("SELECT COALESCE(SUM(tokens_in+tokens_out),0) n FROM ai_usage WHERE created_at>=date_trunc('day',NOW())").fetchone()['n'];from services.core.env_config import env
 budget=int(env('AI_DAILY_TOKEN_BUDGET','0') or 0)
 out['site_tokens']={'daily_budget':budget,'used':int(tokens),'remaining':max(0,budget-int(tokens)) if budget else None,'zero_budget_semantics':'existing setting has no token ceiling; account call quota still applies'}
(root/'institutional-workflow/runtime/verification/codex-factor-cr099-20261109/preload-readonly.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False))
