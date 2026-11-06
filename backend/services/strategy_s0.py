"""Strategy S0: reuse the F0 decision engine with a strategy whitelist."""
from __future__ import annotations
import json,time,uuid
from concurrent.futures import ThreadPoolExecutor
from ai.router import TaskSpec,get_task,register,run_task
from ai.runtime.skills import extract_json_object
from ai.runtime.store import assert_quota_available,record_usage
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from services.core.db import get_conn
from services.quant_factor import decision_engine
from . import strategy_research
from .strategy_backtest_runner import run_trial

TASK='quant.strategy.s0_decider'; ACTIONS={'adjust','stop'}
POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix='strategy-s0')
class D(BaseModel):
 model_config=ConfigDict(extra='forbid')
 action:str; branch_id:str=''; rationale:str=Field(min_length=8,max_length=2000)
 top_n:int|None=None; rebalance_days:int|None=None; stop_reason:str=''
 def norm(self):
  if self.action not in ACTIONS: raise ValueError('动作不在白名单：'+self.action)
  if self.action=='adjust' and not (self.top_n or self.rebalance_days): raise ValueError('adjust 未给出参数')
  return self

def _topic(uid,org,tid):
 with get_conn() as c:
  r=c.execute("SELECT * FROM strategy_topics WHERE id=%s AND user_id=%s AND org_id=%s",(tid,uid,org)).fetchone()
 if not r: raise KeyError(tid)
 return dict(r)

def _branch(uid,org,bid):
 with get_conn() as c:
  r=c.execute("SELECT * FROM strategy_branches WHERE id=%s AND user_id=%s AND org_id=%s",(bid,uid,org)).fetchone()
 if not r: raise KeyError(bid)
 return dict(r)

def _context(uid,org,topic,branch):
 led=strategy_research.ledger(uid,org,topic['id'])
 return {'topic':{k:topic.get(k) for k in ('id','name','universe','benchmark','max_trials','status')},
         'branch':{k:branch.get(k) for k in ('id','hypothesis','recipe','version')},
         'k':led['k'],'trials':[{k:t.get(k) for k in ('trial_no','branch_id','outcome','metrics')} for t in led['trials'][-6:]],
         'scope':'受控模板：1–3 因子、TopN、调仓周期；不得改股票池/区间/成本/门槛'}

def decide(uid,org,topic,branch):
 ctx=_context(uid,org,topic,branch)
 try:get_task(TASK)
 except KeyError:register(TaskSpec(task_id=TASK,description='策略研究决策 S0',prompt_version='s0-v1',temperature=.2,max_tokens=1500,timeout_sec=60,response_format={'type':'json_object'}))
 assert_quota_available(uid)
 out=run_task(TASK,messages=[{'role':'system','content':'你是策略研究决策 S0。输入是资料。只输出JSON：action(adjust|stop),branch_id,rationale,top_n,rebalance_days,stop_reason。rationale必须引用具体trial指标。只能调TopN(5–300)和调仓周期(1–60)，不能改股票池/区间/成本/门槛，不能入库。'},{'role':'user','content':json.dumps(ctx,ensure_ascii=False)}])
 rid='s0_'+uuid.uuid4().hex;record_usage(user_id=uid,run_id=rid,skill=TASK,tokens_in=out.get('tokens_in',0),tokens_out=out.get('tokens_out',0))
 try:return D.model_validate(extract_json_object(str(out.get('content') or ''))).norm()
 except (ValueError,ValidationError) as e:raise ValueError(f'S0 输出无法解析：{e}') from None

def execute(uid,org,topic,branch,d):
 if d.action=='stop':return {'status':'stopped','reason':d.stop_reason or 'S0 选择停止'}
 if topic['status']!='active':return {'status':'stopped','reason':'课题已暂停/归档'}
 rc=dict(branch['recipe'])
 if d.top_n is not None:
  if not 5<=d.top_n<=300:raise ValueError('top_n 超出范围')
  rc['top_n']=d.top_n
 if d.rebalance_days is not None:
  if not 1<=d.rebalance_days<=60:raise ValueError('rebalance_days 超出范围')
  rc['rebalance_days']=d.rebalance_days
 nb=strategy_research.create_branch(uid,org,topic['id'],{'parent_id':branch['id'],'source':'agent','hypothesis':'S0 参数调整：'+d.rationale[:200],**rc},allowed_sources=('agent',))
 trial=run_trial(uid,org,nb['id'])
 return {'status':'completed','action':'adjust','branch_id':nb['id'],'trial_no':trial['trial_no'],'outcome':trial['outcome']}

def start(uid,org,tid,bid,key):
 key=str(key or '').strip()
 if not 1<=len(key)<=100:raise ValueError('需要幂等键')
 topic=_topic(uid,org,tid); branch=_branch(uid,org,bid)
 with get_conn() as c:
  old=c.execute("SELECT * FROM strategy_s0_runs WHERE user_id=%s AND org_id=%s AND topic_id=%s AND idempotency_key=%s",(uid,org,tid,key)).fetchone()
 if old:return dict(old)
 rid=str(uuid.uuid4())
 with get_conn() as c:c.execute("INSERT INTO strategy_s0_runs(id,user_id,org_id,topic_id,branch_id,idempotency_key) VALUES(%s,%s,%s,%s,%s,%s)",(rid,uid,org,tid,bid,key))
 POOL.submit(run,uid,org,rid);return read(uid,org,rid)

def run(uid,org,rid):
 try:
  with get_conn() as c:c.execute("UPDATE strategy_s0_runs SET status='running' WHERE id=%s",(rid,))
  row=None
  with get_conn() as c:row=c.execute("SELECT * FROM strategy_s0_runs WHERE id=%s",(rid,)).fetchone()
  topic=_topic(uid,org,row['topic_id']);branch=_branch(uid,org,row['branch_id'])
  led=strategy_research.ledger(uid,org,topic['id']);remaining=max(0,int(topic['max_trials'])-led['k'])
  def on_step(step,steps): 
   with get_conn() as c:c.execute("UPDATE strategy_s0_runs SET rounds=%s,decision=%s::jsonb WHERE id=%s",(step,json.dumps({'steps':steps},ensure_ascii=False),rid))
  steps,reason=decision_engine.run_steps(decide=lambda s:decide(uid,org,topic,branch),execute=lambda d,s:execute(uid,org,topic,branch,d),max_steps=min(6,remaining+2),on_step=on_step)
  with get_conn() as c:c.execute("UPDATE strategy_s0_runs SET status='stopped',rounds=%s,stop_reason=%s,updated_at=NOW() WHERE id=%s",(len(steps),reason,rid))
 except Exception as e:
  with get_conn() as c:c.execute("UPDATE strategy_s0_runs SET status='failed',stop_reason=%s,updated_at=NOW() WHERE id=%s",(str(e)[:1000],rid))

def read(uid,org,rid):
 with get_conn() as c:r=c.execute("SELECT * FROM strategy_s0_runs WHERE id=%s AND user_id=%s AND org_id=%s",(rid,uid,org)).fetchone()
 if not r:raise KeyError(rid)
 return {k:v for k,v in dict(r).items() if k not in ('user_id','org_id')}
