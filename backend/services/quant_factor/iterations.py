"""Bounded development search with immutable gates, one OOS check and human review.

The worker calls the existing drafting, validation, RE and research-review services.
Only code may change. Concurrent manual edits stop the worker, never get overwritten.
A cancelled/restarted process cannot publish or approve a candidate.
"""
import copy
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from services.core.db import get_conn
from services.factor.detect_store import get_project,_row_project
from . import agent_jobs,service,store
from .policy import WorkflowError,snapshot,digest

POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix='quant-factor-iterate')
ACTIVE=('queued','running')

class Stopped(Exception):pass

def public(row):return {k:v for k,v in dict(row).items() if k not in ('user_id','org_id')}
def read(uid,org,jid):
 with get_conn() as c:
  row=c.execute('SELECT * FROM quant_factor_iterations WHERE id=%s AND user_id=%s AND org_id=%s',(jid,uid,org)).fetchone()
 if not row:raise KeyError(jid)
 if row['status'] in ACTIVE and (datetime.now(timezone.utc)-row['updated_at']).total_seconds()>300:
  finish(uid,org,jid,'failed','运行心跳中断，已保留每轮证据；不会自动重复提交。')
  return read(uid,org,jid)
 return public(row)

def latest(uid,org,pid):
 get_project(uid,pid)
 with get_conn() as c:
  row=c.execute('SELECT id FROM quant_factor_iterations WHERE user_id=%s AND org_id=%s AND project_id=%s ORDER BY created_at DESC LIMIT 1',(uid,org,pid)).fetchone()
 return read(uid,org,row['id']) if row else None

def log(uid,org,jid,action,message,**details):
 with get_conn() as c:
  r=c.execute("UPDATE quant_factor_iterations SET events=events||%s::jsonb,updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status IN ('queued','running') RETURNING id",(store.encode([service.event(action,message=message,**details)]),jid,uid,org)).fetchone()
 if not r:raise Stopped()

def finish(uid,org,jid,status,reason):
 with get_conn() as c:
  c.execute("UPDATE quant_factor_iterations SET status=%s,stop_reason=%s,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status IN ('queued','running')",(status,reason,store.encode([service.event(status,message=reason)]),jid,uid,org))

def checkpoint(uid,org,jid,expected=None):
 row=read(uid,org,jid)
 if row['status'] not in ACTIVE:raise Stopped()
 if expected is not None:
  p=get_project(uid,row['project_id'])['project']
  if digest(snapshot(p))!=expected:raise WorkflowError('研究输入被人工修改，自动迭代停止；未覆盖人工修改。')
 with get_conn() as c:c.execute("UPDATE quant_factor_iterations SET updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status IN ('queued','running')",(jid,uid,org))
 return row

def validation_seen(candidates,plan):
 # No restarting search on a holdout interval already inspected in this project.
 for c in candidates:
  if c.get('evidence',{}).get('validation'):
   p=c['snapshot']['plan']
   if plan['validationStart']<=p['validationEnd'] and p['validationStart']<=plan['validationEnd']:return True
 return False

def start(uid,org,pid,max_rounds):
 if isinstance(max_rounds,bool) or not isinstance(max_rounds,int) or not 1<=max_rounds<=20:raise WorkflowError('自动迭代轮数须为1—20的整数。')
 with get_conn() as c:
  c.execute('SELECT pg_advisory_xact_lock(%s,%s)',(9109,uid))
  old=c.execute("SELECT id FROM quant_factor_iterations WHERE user_id=%s AND org_id=%s AND project_id=%s AND status IN ('queued','running')",(uid,org,pid)).fetchone()
  if old:jid=old['id']
  else:
   p=c.execute('SELECT * FROM detect_projects WHERE user_id=%s AND id=%s FOR UPDATE',(uid,pid)).fetchone()
   if not p:raise KeyError(pid)
   snap=snapshot(_row_project(dict(p)))
   if snap['plan'].get('researchPurpose') not in ('discovery','replication'):raise WorkflowError('请在 F2 明确本次是新因子挖掘还是已有因子复现，再开始自动研究。')
   drafting=c.execute("SELECT id FROM quant_factor_agent_jobs WHERE user_id=%s AND org_id=%s AND project_id=%s AND status IN ('queued','running') LIMIT 1",(uid,org,pid)).fetchone()
   if drafting:raise WorkflowError('本研究仍有 Agent 正在填写，请保存其结果或人工接管后再启动自动迭代。')
   candidates=[dict(r) for r in c.execute('SELECT snapshot,evidence,status FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s',(uid,org,pid)).fetchall()]
   if any(x['status'].endswith('_running') for x in candidates):raise WorkflowError('已有检验正在执行，请等计算结束再启动自动迭代。')
   if validation_seen(candidates,snap['plan']):raise WorkflowError('该样本外区间已被本研究查看过。请先人工复盘并登记新的未使用验证区间，不能继续针对已看过的验证集调参。')
   remaining=snap['plan']['maxTrials']-len(candidates)
   if remaining<=0:raise WorkflowError('已达到研究总尝试预算，请先人工复盘。')
   if max_rounds>remaining:raise WorkflowError(f'剩余研究尝试预算 {remaining} 次，本次请求 {max_rounds} 轮；请减少轮数或先复盘修订计划。')
   pending=c.execute("SELECT COUNT(*) AS n FROM quant_factor_iterations WHERE user_id=%s AND org_id=%s AND status IN ('queued','running')",(uid,org)).fetchone()['n']
   if pending>=1:raise WorkflowError('自动研究队列繁忙，请稍后再试。')
   jid=str(uuid.uuid4())
   if snap['plan'].get('researchPurpose')=='discovery':
    from .asset_context import catalogue
    snap['_library_reference']=catalogue(uid)
   c.execute("INSERT INTO quant_factor_iterations(id,user_id,org_id,project_id,status,max_rounds,baseline,events) VALUES(%s,%s,%s,%s,'queued',%s,%s::jsonb,%s::jsonb)",(jid,uid,org,pid,max_rounds,store.encode(snap),store.encode([service.event('queued',message='已固定研究计划、数据范围、交易参数与硬门槛。',max_rounds=max_rounds)])))
 if not old:POOL.submit(run,uid,org,jid)
 return read(uid,org,jid)

def remember_child(uid,org,jid,field,value):
 assert field in ('candidate_id','agent_job_id')
 with get_conn() as c:
  r=c.execute(f"UPDATE quant_factor_iterations SET {field}=%s,updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status IN ('queued','running') RETURNING id",(value,jid,uid,org)).fetchone()
 if not r:raise Stopped()

def save_round(uid,org,jid,number,candidate,change):
 entry={'number':number,'candidate_id':candidate['id'],'status':candidate['status'],'snapshot_hash':candidate['snapshot_hash'],'change':change,'factor_name':candidate['snapshot']['request']['factor_name'],'evidence':{k:{'gate':v.get('gate'),'report_id':v.get('report_id'),'run_id':v.get('run_id'),'novelty':v.get('novelty')} for k,v in candidate['evidence'].items()}}
 with get_conn() as c:
  r=c.execute("UPDATE quant_factor_iterations SET rounds=(SELECT COALESCE(jsonb_agg(x),'[]'::jsonb) FROM jsonb_array_elements(rounds) x WHERE (x->>'number')::int<>%s)||%s::jsonb,updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status IN ('queued','running') RETURNING id",(number,store.encode([entry]),jid,uid,org)).fetchone()
 if not r:raise Stopped()

def wait_candidate(uid,org,jid,cid,expected):
 deadline=time.monotonic()+2220
 while time.monotonic()<deadline:
  checkpoint(uid,org,jid,expected)
  c=service.current(uid,org,cid)
  if not c['status'].endswith('_running'):return c
  time.sleep(2)
 raise WorkflowError('计算等待超时，已保留工具任务编号。')

def wait_agent(uid,org,jid,aid,expected):
 deadline=time.monotonic()+240
 while time.monotonic()<deadline:
  checkpoint(uid,org,jid,expected)
  a=agent_jobs.read(uid,org,aid)
  if a['status'] not in agent_jobs.ACTIVE:
   if a['status']!='ready':raise WorkflowError('因子改进未完成：'+a['events'][-1].get('message','请检查 Agent 记录'))
   return a
  time.sleep(2)
 raise WorkflowError('Agent 改进超时；保留输入与已完成证据。')

def apply_code(uid,org,jid,expected,fields):
 """Compare-and-set under both loop and project locks; no overwrite after pause."""
 from services.factor.code_validation import validated_factor_code
 validated_factor_code(fields['code'],fields['name'])
 with get_conn() as c:
  loop=c.execute('SELECT * FROM quant_factor_iterations WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(jid,uid,org)).fetchone()
  if not loop or loop['status'] not in ACTIVE:raise Stopped()
  row=c.execute('SELECT * FROM detect_projects WHERE user_id=%s AND id=%s FOR UPDATE',(uid,loop['project_id'])).fetchone()
  p=_row_project(dict(row))
  if digest(snapshot(p))!=expected:raise WorkflowError('研究输入已由人工修改，未写入 Agent 的改进。')
  cfg=copy.deepcopy(p['config']);cfg.update(factorCodes=[fields['name']],weights=[1],powers=[1],draftFactors=None,draftFactor={'name':fields['name'],'body':fields['code'],'description':cfg['researchPlan']['hypothesis'],'category':'机构迭代研究'})
  p['config']=cfg;p['factorName']=fields['name'];next_hash=digest(snapshot(p))
  c.execute('UPDATE detect_projects SET factor_name=%s,config=%s::jsonb,updated_at=NOW() WHERE user_id=%s AND id=%s',(fields['name'],store.encode(cfg),uid,loop['project_id']))
 return next_hash

def cleanup_children(uid,org,row):
 if row.get('agent_job_id'):
  try:agent_jobs.cancel(uid,org,row['agent_job_id'])
  except (KeyError,WorkflowError):pass
 if row.get('candidate_id') and row.get('status')!='paused':
  try:
   c=service.current(uid,org,row['candidate_id'])
   if c['status'].endswith('_running'):service.cancel(uid,org,c['id'])
  except (KeyError,WorkflowError):pass

def pause(uid,org,jid):
 row=read(uid,org,jid)
 finish(uid,org,jid,'paused','人工暂停：停止后续改进与送审；已提交的固定版本计算继续完成并留档，不重复计费重跑。')
 cleanup_children(uid,org,{**row,'status':'paused'})
 return read(uid,org,jid)

def submit_research(uid,org,jid,candidate,number,expected):
 # Serialize pause vs handoff on the iteration row. Review remains a separate human action.
 from .review import request_review
 checkpoint(uid,org,jid,expected)
 from .novelty_policy import handoff_allowed
 purpose='新因子候选（已通过冻结库范围去重）' if candidate['snapshot']['plan'].get('researchPurpose')=='discovery' else '已有因子复现（不申报新发现）'
 note=purpose+f'，自动迭代第{number}轮通过预登记研发和样本外数值门槛。版本：{candidate["snapshot_hash"]}。属于待人工复核的研究证据；未封存、未正式准入，不代表投资建议。'
 with get_conn() as c:
  loop=c.execute('SELECT status FROM quant_factor_iterations WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(jid,uid,org)).fetchone()
  if not loop or loop['status'] not in ACTIVE:raise Stopped()
  if candidate['snapshot']['plan'].get('researchPurpose')!='replication' and not handoff_allowed(candidate):raise WorkflowError('未取得完整、通过的因子库去重证据，不自动送审为新成果。')
  service.archive(uid,org,candidate['id'],note)
  request_review(uid,org,candidate['id'],'请独立核对经济解释、数据覆盖、交易成本、重复试验与样本外证据。'+note)
  reason='研发与样本外硬门槛通过，已整理证据送交独立研究复核；未自动审批或正式准入。'
  c.execute("UPDATE quant_factor_iterations SET status='review_pending',stop_reason=%s,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s",(reason,store.encode([service.event('review_pending',message=reason)]),jid,uid,org))

def run(uid,org,jid):
 expected=None;data_release=None;reference_source=None
 try:
  row=checkpoint(uid,org,jid);pid=row['project_id'];baseline=copy.deepcopy(row['baseline']);reference=baseline.pop('_library_reference',None);expected=digest(baseline);change='检验已保存的初始实现。'
  with get_conn() as c:c.execute("UPDATE quant_factor_iterations SET status='running',updated_at=NOW() WHERE id=%s AND user_id=%s AND org_id=%s AND status='queued'",(jid,uid,org))
  for number in range(1,row['max_rounds']+1):
   checkpoint(uid,org,jid,expected)
   log(uid,org,jid,'development',f'第 {number} 轮：冻结实现并调用真实研发检验。',round=number,tool='ResearchEngine.factor')
   candidate=service.create(uid,org,pid,expected,reference=reference)
   try:remember_child(uid,org,jid,'candidate_id',candidate['id'])
   except Stopped:
    if candidate['status'].endswith('_running'):service.cancel(uid,org,candidate['id'])
    raise
   candidate=wait_candidate(uid,org,jid,candidate['id'],expected)
   save_round(uid,org,jid,number,candidate,change)
   release=candidate['evidence'].get('development',{}).get('result',{}).get('meta',{}).get('data_release_id')
   if data_release is not None and release!=data_release:raise WorkflowError('迭代期间数据版本发生变化，停止跨版本比较；已有证据保留。')
   if release:data_release=release
   ref_source=candidate['evidence'].get('development',{}).get('novelty',{}).get('meta',{}).get('reference_source_hash')
   if reference_source and ref_source and reference_source!=ref_source:raise WorkflowError('对照因子源码版本变化，停止跨版本搜索。')
   if ref_source:reference_source=ref_source
   if candidate['status']=='development_passed':
    log(uid,org,jid,'validation',f'第 {number} 轮研发门槛通过，执行一次固定样本外复验。',round=number)
    checkpoint(uid,org,jid,expected);service.validate(uid,org,candidate['id'])
    candidate=wait_candidate(uid,org,jid,candidate['id'],expected);save_round(uid,org,jid,number,candidate,change)
    if candidate['status']=='validation_passed':submit_research(uid,org,jid,candidate,number,expected)
    elif candidate['status']=='validation_failed':finish(uid,org,jid,'validation_failed','样本外门槛未通过。本轮研究停止，不针对已经查看的验证集继续调参；证据保留待人工复盘。')
    else:raise WorkflowError('样本外计算未完成，请核对保留的执行记录。')
    return
   if candidate['status']!='development_failed':raise WorkflowError(candidate.get('evidence',{}).get('development',{}).get('novelty',{}).get('message') or '研发计算异常或被取消；停止迭代，不把执行错误当成因子质量结论。')
   if number>=row['max_rounds']:
    finish(uid,org,jid,'limit_reached','已达到本次最大迭代轮数，候选尚未通过研发门槛。所有失败实验保留，不送审。');return
   checks=candidate['evidence']['development']['gate']['checks'];failed=[c['name'] for c in checks if not c['passed']]
   novelty=candidate['evidence']['development'].get('novelty') or {}
   if novelty.get('status')=='failed':failed.append('因子库去重')
   log(uid,org,jid,'improvement',f'第 {number} 轮未通过：'+'、'.join(failed)+'。Agent 仅依据研发结果改进实现。',round=number+1,tool='research.generate_factor')
   checkpoint(uid,org,jid,expected)
   p=get_project(uid,pid)['project'];plan=p['config']['researchPlan'];draft=p['config'].get('draftFactor') or {}
   # Holdout results are never included in model context.
   feedback={'checks':[{k:x[k] for k in ('name','actual','operator','threshold','passed')} for x in checks],'novelty':{'status':novelty.get('status'),'max_abs_correlation':novelty.get('gate',{}).get('max_abs_correlation'),'closest':{k:v for k,v in (novelty.get('gate',{}).get('closest') or {}).items() if k in ('reference_id','factor_name','mean_abs_spearman')},'duplicates':novelty.get('duplicates',[])[:3]}}
   hypothesis=plan['hypothesis']+'\n请基于下列研发反馈改进因子实现。不得改研究门槛、数据区间、交易参数，不得利用未来数据或验证集；保持经济假设一致，不能为过门槛伪造值。\n'+store.encode(feedback)
   a=agent_jobs.create(uid,org,'F3',pid,{'hypothesis':hypothesis,'candidateExpression':plan.get('candidateExpression',''),'improvementScope':plan.get('improvementScope','仅修复初始定义的实现，禁止改变窗口、公式语义和方向。'),'mode':'improve','target':plan.get('target',''),'name':draft.get('name') or p['config']['factorCodes'][0],'code':draft.get('body') or candidate['snapshot']['request'].get('factor_code','')},jid+':'+str(number+1))
   try:remember_child(uid,org,jid,'agent_job_id',a['id'])
   except Stopped:agent_jobs.cancel(uid,org,a['id']);raise
   a=wait_agent(uid,org,jid,a['id'],expected);fields=a['output']['fields']
   if fields['code'].strip()==candidate['snapshot']['request'].get('factor_code','').strip():
    finish(uid,org,jid,'limit_reached','Agent 未产生新的实现，停止重复计算；保留现有结果待人工改进。');return
   expected=apply_code(uid,org,jid,expected,fields)
   change='针对 '+ '、'.join(failed)+' 改进实现；原始代码及修改后的代码分别保存在每轮冻结快照中。'
   log(uid,org,jid,'code_saved',f'第 {number+1} 轮实现已通过静态校验并写入 F3。',round=number+1,agent_job_id=a['id'],factor_name=fields['name'])
 except Stopped:
  try:cleanup_children(uid,org,read(uid,org,jid))
  except Exception:pass
 except Exception as exc:
  message=str(exc) if isinstance(exc,(WorkflowError,PermissionError,ValueError)) else '自动研究发生服务异常，已保留每轮证据，请检查服务后重试。'
  finish(uid,org,jid,'failed',message[:1000])
  try:cleanup_children(uid,org,read(uid,org,jid))
  except Exception:pass
