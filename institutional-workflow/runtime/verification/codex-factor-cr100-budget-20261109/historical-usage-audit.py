"""Read-only aggregate provenance audit; never records prompts, output, credentials or user text."""
from pathlib import Path
import sys,os,json,datetime
root=Path(__file__).resolve().parents[4];sys.path.insert(0,str(root/'backend'))
from services.core.db import database_url
import psycopg
from psycopg.rows import dict_row
out={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'read_only':True,'scope':'quant tables and referenced ai_usage aggregates; not site usage as module usage'}
with psycopg.connect(database_url(),row_factory=dict_row,options='-c default_transaction_read_only=on') as c:
 c.execute("SET LOCAL statement_timeout='5s'")
 out['quant_agent_usage_by_stage']=[dict(r) for r in c.execute("SELECT j.org_id,j.user_id,j.stage,COUNT(DISTINCT j.id) jobs,COUNT(u.id) usage_rows,COALESCE(SUM(u.tokens_in+u.tokens_out),0) measured_tokens,COUNT(u.id) FILTER(WHERE u.tokens_in+u.tokens_out=0) zero_token_rows FROM quant_factor_agent_jobs j LEFT JOIN ai_usage u ON u.run_id=j.id AND u.user_id=j.user_id GROUP BY j.org_id,j.user_id,j.stage ORDER BY j.org_id,j.user_id,j.stage")]
 out['f0_step_usage']=[dict(r) for r in c.execute("SELECT r.org_id,r.user_id,COUNT(*) steps,COALESCE(SUM((s->'usage'->>'tokens_in')::bigint+(s->'usage'->>'tokens_out')::bigint),0) recorded_tokens,COUNT(*) FILTER(WHERE s->'usage'->>'tokens_in' IS NULL OR s->'usage'->>'tokens_out' IS NULL) missing_usage_steps FROM quant_factor_f0_runs r CROSS JOIN LATERAL jsonb_array_elements(COALESCE(r.decision->'steps','[]'::jsonb)) s GROUP BY r.org_id,r.user_id ORDER BY r.org_id,r.user_id")]
 out['quant_specific_ai_usage']=[dict(r) for r in c.execute("SELECT skill,COUNT(*) rows,SUM(tokens_in+tokens_out) measured_tokens,COUNT(*) FILTER(WHERE tokens_in+tokens_out=0) zero_token_rows FROM ai_usage WHERE skill LIKE 'quant.factor.%%' GROUP BY skill ORDER BY skill")]
 out['assistant_output_references']=[dict(r) for r in c.execute("SELECT j.org_id,j.user_id,j.stage,COUNT(*) linked_rows,COALESCE(SUM(u.tokens_in+u.tokens_out),0) measured_tokens FROM quant_factor_agent_jobs j JOIN ai_usage u ON u.run_id=j.output->>'run_id' AND u.user_id=j.user_id GROUP BY j.org_id,j.user_id,j.stage")]
 out['ai_usage_has_immutable_org_project_columns']=False
(root/'institutional-workflow/runtime/verification/codex-factor-cr100-budget-20261109/historical-usage-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=int)+'\n');print(json.dumps(out,ensure_ascii=False,default=int))
