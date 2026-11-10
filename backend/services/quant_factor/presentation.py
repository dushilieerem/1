"""Read-only research identity: trial/branch/execution, never inferred from UUID order."""
from .policy import digest


def branch_sources(branch,trial=None):
 source=(branch or {}).get('source');parent=(branch or {}).get('parent_id')
 creation='人工建立课题' if source=='manual' and not parent else '人工接手' if source=='manual' else '研究系统修订' if source=='agent' else '建立方式未记录'
 executor=(trial or {}).get('executor')
 execution={'human':'研究员执行','agent':'研究系统执行','service':'计算服务执行'}.get(executor,'尚无执行记录')
 return {'creation_label':creation,'execution_label':execution,'execution_source':executor}


def context(uid,org,project_id):
 from . import ledger
 from .repo import topics
 from services.core.tenant import Tenant
 matches=topics(Tenant.from_pair(uid,org),project_id)
 if len(matches)!=1:return {'branches':{},'trials':[],'labels':{},'topic_id':None}
 topic=matches[0];branches=ledger._branches(uid,org,topic['id']);trials=ledger._trials(uid,org,topic['id'])
 return {'branches':{b['id']:b for b in branches},'trials':trials,'labels':ledger._branch_labels(uid,org,topic['id'],branches),'topic_id':topic['id']}


def candidate_identity(row,facts):
 matches=[trial for trial in facts['trials'] if trial.get('report_id')=='qf_'+row['id']+'_development']
 branches={trial['branch_id'] for trial in matches if trial.get('branch_id')};stored=(row.get('evidence') or {}).get('branch_id')
 if isinstance(stored,str) and stored:branches.add(stored)
 branch_id=next(iter(branches)) if len(branches)==1 else None
 conflict=len(branches)>1
 branch=facts['branches'].get(branch_id) or {};label=facts['labels'].get(branch_id)
 numbers=sorted({int(trial['trial_no']) for trial in matches if isinstance(trial.get('trial_no'),int)})
 latest=max(matches,key=lambda t:t.get('trial_no') or 0) if matches else None
 return {'trial_no':numbers[-1] if numbers else None,'trial_numbers':numbers,'branch_id':branch_id,'branch_label':label,
         'relation_status':'conflict' if conflict else 'matched' if label else 'unrecorded',
         **branch_sources(branch,latest),'topic_id':facts.get('topic_id')}


def checkout_config(current,candidate,new_branch_id):
 """Copy exactly a selected immutable definition to a new manual draft, not its approval."""
 import copy
 config=copy.deepcopy(current);snap=candidate['snapshot']
 if digest(snap)!=candidate['snapshot_hash']:raise ValueError('所选候选与冻结指纹不一致，不能接手')
 request=snap['request'];name=request['factor_name'];plan=copy.deepcopy(snap['plan'])
 plan['revision']='manual-'+new_branch_id
 config.update(researchPlan=plan,factorCodes=[name],weights=[1],powers=[1],v5ActiveBranch=new_branch_id,
               sourceResearchCandidate={'id':candidate['id'],'snapshot_hash':candidate['snapshot_hash'],'purpose':'research_only','inherits_approval':False})
 config.pop('draftFactors',None)
 if request.get('factor_code'):
  config['draftFactor']={'name':name,'body':request['factor_code'],'description':plan.get('hypothesis') or '', 'category':'机构因子研究'}
  config['factorLibraries']={}
 else:
  config['draftFactor']=None;config['factorLibraries']={name:request['library_name']}
 mapping={'universe':'universe','benchmark':'benchmark','portfolio_type':'portfolioType','groups':'groups','rebalance_days':'rebalanceDays','execution_timing':'executionTiming','commission_rate':'commissionRate','stamp_tax':'stampTax','slippage_rate':'slippageRate','filter_suspended':'filterSuspended','filter_st':'filterSt','filter_limit_up':'filterLimitUp','filter_limit_down':'filterLimitDown'}
 for source,destination in mapping.items():
  if source in request:config[destination]=copy.deepcopy(request[source])
 config['researchUniverseSymbols']=copy.deepcopy((request.get('universe_snapshot') or {}).get('symbols') or [])
 if snap.get('sourceResearchAsset'):config['sourceResearchAsset']=copy.deepcopy(snap['sourceResearchAsset'])
 else:config.pop('sourceResearchAsset',None)
 config.update(rangeMode='custom',startDate=plan['developmentStart'],endDate=plan['developmentEnd'])
 return config


def workbench(uid,org,project_id):
 from services.core.db import get_conn
 from services.factor.detect_store import _row_project
 from .policy import snapshot,WorkflowError
 from .repo import topics
 from services.core.tenant import Tenant
 if len(topics(Tenant.from_pair(uid,org),project_id))!=1:raise KeyError(project_id)
 with get_conn() as c:row=c.execute('SELECT * FROM detect_projects WHERE user_id=%s AND id=%s',(uid,project_id)).fetchone()
 if not row:raise KeyError(project_id)
 project=_row_project(dict(row));config=project['config'];out={'branch_id':config.get('v5ActiveBranch'),'control_epoch':config.get('v5ControlEpoch'),'factor_name':(config.get('factorCodes') or [''])[0]}
 marker=config.get('v5ManualVersion') or {}
 out['requires_handoff']=bool(marker.get('branch_id')==out['branch_id'] and marker.get('source')=='human_workbench_save')
 try:out.update(snapshot_hash=digest(snapshot(project)),can_handoff=bool(out['branch_id'] and out['control_epoch']))
 except WorkflowError as exc:out.update(snapshot_hash=None,can_handoff=False,reason=str(exc))
 return out


def save_workbench(uid,org,project_id,payload):
 """V5-only atomic manual save; legacy projects retain their existing adapter."""
 import uuid
 from services.core.db import get_conn
 from services.factor.detect_store import _row_project
 from . import ledger,store
 with get_conn() as c:
  topics=c.execute('SELECT * FROM quant_factor_topics WHERE user_id=%s AND project_id=%s',(uid,project_id)).fetchall()
  if not topics:return None
  if len(topics)!=1 or topics[0]['org_id']!=org:raise ValueError('此研究工作稿不属于当前机构')
  topic=dict(topics[0]);row=ledger._lock_workbench(c,uid,org,topic)
  current=row.get('config') or {};config=dict(payload.get('config') or {})
  if config.get('v5ActiveBranch')!=current.get('v5ActiveBranch') or config.get('v5ControlEpoch')!=current.get('v5ControlEpoch'):raise ValueError('工作分支或控制版本已变化，请重新读取后保存，未覆盖当前工程')
  if not current.get('v5ActiveBranch'):raise ValueError('请先明确确认工作分支后保存')
  if c.execute('SELECT id FROM quant_factor_trials WHERE user_id=%s AND org_id=%s AND topic_id=%s AND branch_id=%s LIMIT 1',(uid,org,topic['id'],current['v5ActiveBranch'])).fetchone():raise ValueError('此分支已有冻结试验，请从明确候选接手为新修订后保存')
  from .research_contract import check_project,project_contract
  if project_contract({'config':current})!=project_contract({'config':config}):raise ValueError('已冻结研究契约不可覆盖')
  draft=config.get('draftFactor') or {}
  check_project({'id':project_id,'config':config},draft.get('body') or None,draft.get('name'))
  config['v5ControlEpoch']=str(uuid.uuid4())
  if str((config.get('draftFactor') or {}).get('body') or '').strip() or config.get('factorCodes'):
   config['v5ManualVersion']={'source':'human_workbench_save','branch_id':config['v5ActiveBranch'],'control_epoch':config['v5ControlEpoch']}
  saved=c.execute('UPDATE detect_projects SET name=%s,factor_name=%s,description=%s,config=%s::jsonb,updated_at=NOW() WHERE user_id=%s AND id=%s RETURNING *',(str(payload.get('name') or row['name']),str(payload.get('factorName') or row['factor_name']),str(payload.get('description') or ''),store.encode(config),uid,project_id)).fetchone()
  return {'ok':True,'user_id':uid,'project':_row_project(dict(saved))}
