"""Explicit PM-created task only: read-only status/receipts, never dispatch."""
import os,sys,json,datetime,hashlib
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
root=Path(__file__).resolve().parents[4];pid=int(sys.argv[1]);project_id=sys.argv[2]
os.environ.update(dict(item.split('=',1) for item in Path('/proc/'+str(pid)+'/environ').read_bytes().decode().split('\0') if '=' in item));os.environ['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1';sys.path.insert(0,str(root/'backend'))
from services.core.db import database_url
from services.quant_factor.ledger import current_k
record={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'project_id':project_id,'read_only_transaction':True,'no_dispatch_or_mutation':True}
with psycopg.connect(database_url(),row_factory=dict_row,options='-c default_transaction_read_only=on -c statement_timeout=5000') as c:
 project=c.execute('SELECT config FROM detect_projects WHERE id=%s AND user_id=%s',(project_id,2527)).fetchone();assert project
 cfg=project['config'];plan=cfg.get('researchPlan') or {};record['contract']=plan.get('researchContract');record['scope']={'static_symbols':len(cfg.get('researchUniverseSymbols') or []),'development':[plan.get('developmentStart'),plan.get('developmentEnd')],'validation':[plan.get('validationStart'),plan.get('validationEnd')],'max_trials':plan.get('maxTrials'),'active_branch':cfg.get('v5ActiveBranch'),'control_epoch':cfg.get('v5ControlEpoch')}
 topic=c.execute('SELECT id,status,primary_holding_period FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s',(2527,261,project_id)).fetchone();record['topic']=topic
 run=c.execute('SELECT id,status,rounds,stop_reason,decision FROM quant_factor_f0_runs WHERE user_id=%s AND org_id=%s AND project_id=%s ORDER BY created_at DESC LIMIT 1',(2527,261,project_id)).fetchone();record['f0']=run
 record['jobs']=c.execute("SELECT id,stage,status,input->'controller' AS controller,events,output->'research_method' AS method,output->'fields' AS fields FROM quant_factor_agent_jobs WHERE user_id=%s AND org_id=%s AND project_id=%s ORDER BY created_at DESC LIMIT 4",(2527,261,project_id)).fetchall()
 for job in record['jobs']:
  fields=job.pop('fields',None) or {};source=fields.get('code') or '';job['source_sha256']=hashlib.sha256(source.encode()).hexdigest() if source else None;job['entry']=fields.get('name')
 record['candidates']=c.execute("SELECT id,status,snapshot_hash,evidence->>'branch_id' AS branch_id,evidence->'method' AS method,jsonb_build_object('run_id',evidence->'development'->'run_id','report_id',evidence->'development'->'report_id','gate',evidence->'development'->'gate','metrics',evidence->'development'->'result'->'metrics','meta',evidence->'development'->'result'->'meta','novelty',evidence->'development'->'novelty') AS development FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s ORDER BY created_at LIMIT 4",(2527,261,project_id)).fetchall()
 record['trials']=c.execute('SELECT trial_no,branch_id,outcome,kind,holding_period,returned_metrics,report_id FROM quant_factor_trials WHERE user_id=%s AND org_id=%s AND project_id=%s ORDER BY trial_no',(2527,261,project_id)).fetchall();record['k']=current_k(record['trials'],topic['primary_holding_period'])
 record['model_calls']=c.execute("SELECT id,task_id,call_key,request_hash,prompt_upper_tokens,max_output_tokens,status,reserved_tokens,actual_tokens,created_at,updated_at,response->>'finish_reason' AS finish_reason,response->'usage' AS usage,response->>'error_type' AS error_type FROM quant_ai_budget_calls WHERE org_id=%s AND user_id=%s AND project_id=%s ORDER BY created_at",(261,2527,project_id)).fetchall()
record['process_resources']={}
for process_id in [pid,2045830]:
 try:record['process_resources'][str(process_id)]={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in Path('/proc/'+str(process_id)+'/status').read_text().splitlines() if line.startswith(('VmRSS:','VmSize:','Threads:'))}
 except OSError:record['process_resources'][str(process_id)]={'state':'not_present'}
record['host_mem_available']=next(line.split(':',1)[1].strip() for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
path=Path(__file__).with_name('live-'+project_id[:8]+'.json');path.write_text(json.dumps(record,ensure_ascii=False,indent=2,default=str)+'\n')
print(json.dumps({'checked_at_utc':record['checked_at_utc'],'method_version':(run.get('decision') or {}).get('method_version') if run else None,'allowed_fields':(record['contract'] or {}).get('allowed_fields'),'f0':{k:run.get(k) for k in ('id','status','rounds','stop_reason')} if run else None,'phase':(run.get('decision') or {}).get('current_phase') if run else None,'jobs':[{k:j.get(k) for k in ('id','stage','status')} for j in record['jobs']],'candidates':[{k:j.get(k) for k in ('id','status')} for j in record['candidates']],'k':record['k'],'model_calls':record['model_calls'],'resources':record['process_resources'],'host_available':record['host_mem_available']},ensure_ascii=False,default=str))
