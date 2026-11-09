"""Exact named task's saved-code/branch/K/result metadata; no actions or code-body export."""
from pathlib import Path
import sys,json,hashlib,datetime
root=Path(__file__).resolve().parents[4];sys.path.insert(0,str(root/'backend'))
from services.core.db import database_url
from services.quant_factor.ledger import current_k
import psycopg
from psycopg.rows import dict_row
project='5cc9d1ce-0362-46a0-8148-23aa7d29458a';out={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'read_only':True,'project_id':project}
sha=lambda text:hashlib.sha256(str(text or '').encode()).hexdigest()
with psycopg.connect(database_url(),row_factory=dict_row,options='-c default_transaction_read_only=on') as c:
 c.execute("SET LOCAL statement_timeout='5s'")
 p=c.execute('SELECT config,updated_at FROM detect_projects WHERE user_id=2527 AND id=%s',(project,)).fetchone();cfg=p['config'];source=(cfg.get('draftFactor') or {}).get('body') or '';out['saved_manual']={'active_branch':cfg.get('v5ActiveBranch'),'source_sha256':sha(source),'has_negative_gap_support':'gap_support' in source and '(-gap).clip(lower=0)' in source,'plan_revision':cfg['researchPlan']['revision'],'updated_at':str(p['updated_at'])}
 f0=[dict(r) for r in c.execute("SELECT id,status,rounds,stop_reason,decision->'manual_handoff' AS manual_handoff,decision->>'current_action' AS current_action FROM quant_factor_f0_runs WHERE project_id=%s ORDER BY created_at DESC LIMIT 2",(project,))];out['f0']=f0;handoff=(f0[0].get('manual_handoff') or {}) if f0 else {}
 topic=c.execute('SELECT id,primary_holding_period,max_trials FROM quant_factor_topics WHERE project_id=%s AND user_id=2527',(project,)).fetchone();trials=[dict(r) for r in c.execute('SELECT trial_no,branch_id,report_id,executor,kind,outcome,holding_period,returned_metrics FROM quant_factor_trials WHERE topic_id=%s ORDER BY trial_no',(topic['id'],))];out['trials']=trials;out['k']=current_k(trials,topic['primary_holding_period']);out['max_trials']=topic['max_trials'];out['candidates']=[]
 for row in c.execute('SELECT id,status,snapshot_hash,snapshot,evidence FROM quant_factor_candidates WHERE project_id=%s AND user_id=2527 ORDER BY updated_at DESC LIMIT 3',(project,)):
  development=(row['evidence'] or {}).get('development') or {};request=row['snapshot']['request'];candidate_source=request.get('factor_code') or '';out['candidates'].append({'id':row['id'],'status':row['status'],'snapshot_hash':row['snapshot_hash'],'matches_handoff_snapshot':row['snapshot_hash']==handoff.get('snapshot_hash'),'source_sha256':sha(candidate_source),'matches_saved_manual_source':candidate_source==source,'branch_id':(row['evidence'] or {}).get('branch_id'),'run_id':development.get('run_id'),'gate':development.get('gate'),'novelty_status':(development.get('novelty') or {}).get('status'),'controlled_execution':((development.get('result') or {}).get('meta') or {}).get('controlled_execution'),'static_symbol_count':len((request.get('universe_snapshot') or {}).get('symbols') or [])})
 out['budget']=[dict(r) for r in c.execute("SELECT task_id,status,actual_tokens,reserved_tokens,max_output_tokens,response->>'finish_reason' AS finish_reason,response->'usage' AS usage FROM quant_ai_budget_calls WHERE project_id=%s ORDER BY created_at",(project,))]
(root/'institutional-workflow/runtime/verification/codex-factor-cr100-budget-20261109/hybrid-handoff-readonly.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str)+'\n');print(json.dumps(out,ensure_ascii=False,default=str))
