"""One explicitly named PM task, metadata-only observation; no research/model actions."""
from pathlib import Path
import sys,json,datetime
root=Path(__file__).resolve().parents[4];sys.path.insert(0,str(root/'backend'))
from services.core.db import database_url
import psycopg
from psycopg.rows import dict_row
project=sys.argv[1];out={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'project_id':project,'read_only':True}
with psycopg.connect(database_url(),row_factory=dict_row,options='-c default_transaction_read_only=on') as c:
 c.execute("SET LOCAL statement_timeout='5s'")
 out['f0']=[dict(r) for r in c.execute("SELECT id,status,rounds,stop_reason,decision->>'current_action' AS current_action,created_at,updated_at FROM quant_factor_f0_runs WHERE project_id=%s ORDER BY created_at DESC LIMIT 2",(project,))]
 out['agent_jobs']=[dict(r) for r in c.execute("SELECT id,stage,status,events->-1 AS last_event,created_at,updated_at FROM quant_factor_agent_jobs WHERE project_id=%s ORDER BY created_at DESC LIMIT 3",(project,))]
 out['candidates']=[dict(r) for r in c.execute("SELECT id,status,evidence->'development'->>'run_id' AS run_id,evidence->'development'->'result'->'meta'->'controlled_execution' AS controlled_execution,updated_at FROM quant_factor_candidates WHERE project_id=%s ORDER BY updated_at DESC LIMIT 3",(project,))]
 out['budget']=[dict(r) for r in c.execute("SELECT id,task_id,status,reserved_tokens,actual_tokens,max_output_tokens,response->>'finish_reason' AS finish_reason,response->'usage' AS usage,created_at,updated_at FROM quant_ai_budget_calls WHERE project_id=%s ORDER BY created_at DESC LIMIT 8",(project,))]
 out['budget_totals']=dict(c.execute("SELECT COALESCE(SUM(actual_tokens) FILTER(WHERE status='settled'),0) AS settled_tokens,COALESCE(SUM(reserved_tokens) FILTER(WHERE status<>'settled'),0) AS held_tokens FROM quant_ai_budget_calls WHERE project_id=%s",(project,)).fetchone())
(root/'institutional-workflow/runtime/verification/codex-factor-cr100-budget-20261109/hybrid-initial-readonly.json').write_text(json.dumps(out,ensure_ascii=False,default=str,indent=2)+'\n');print(json.dumps(out['budget_totals'],default=str))
