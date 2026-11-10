"""Immutable research scope shared by planning, implementation and execution."""
import copy,hashlib,json
VERSION='quant.research-contract.v1'
OHLCV=frozenset(('open','high','low','close','volume'))

def fingerprint(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def freeze(*,data_fields,engine_fields,requested_fields,rules,data_identity,method_identity,explicit_ohlcv=False):
 available=set(data_fields)&set(engine_fields)
 if not available:raise ValueError('发布数据和计算能力尚未共同确认可用字段，未冻结研究契约')
 selected=set(requested_fields) if requested_fields is not None else set(available)
 if explicit_ohlcv:
  if requested_fields is not None and selected!=OHLCV:raise ValueError('已要求仅用OHLCV，请明确确认五个字段，未自动改写输入')
  selected=set(OHLCV)
 if not selected or not selected<=available:raise ValueError('所选字段不在本次已确认数据与计算能力交集内')
 if rules.get('direction') not in ('positive','negative') or rules.get('icMetric') not in ('ic','rank_ic'):raise ValueError('预登记方向或IC口径尚未明确')
 if not data_identity or not method_identity:raise ValueError('数据或计算方法身份未确认')
 out={'schema':VERSION,'allowed_fields':sorted(selected),'available_fields':sorted(available),'field_selection':'explicit_ohlcv' if explicit_ohlcv else 'explicit' if requested_fields is not None else 'available_intersection','direction':rules['direction'],'ic_metric':rules['icMetric'],'forecast_horizon_sessions':1,'rules_hash':fingerprint(rules),'data_identity':copy.deepcopy(data_identity),'method_identity':copy.deepcopy(method_identity)}
 return {**out,'contract_hash':fingerprint(out)}

def check_fields(fields,contract):
 if contract.get('schema')!=VERSION:raise ValueError('旧任务未声明此字段契约；须明确新版本，不回写历史')
 payload={k:v for k,v in contract.items() if k!='contract_hash'}
 if fingerprint(payload)!=contract.get('contract_hash'):raise ValueError('冻结字段契约已变化')
 extra=set(fields)-set(contract['allowed_fields'])
 if extra:raise ValueError('实现超出已冻结字段：'+', '.join(sorted(extra)))
 return True

METHOD_VERSION='bounded-factor-rd-v2'

def from_project(uid, org, project, view):
 from services.quant_data_resources import dataset
 from .source_contract import FIELDS
 from .source_compat import RE_POLICY_SHA256
 from .provenance import _CODE_REVISION
 cfg=project.get('config') or {};plan=cfg.get('researchPlan') or {}
 meta=dataset(uid,org,'daily_bars',view['view_id'])
 if not meta.get('published') or meta.get('catalog_version')!=view['view_id'] or meta.get('publication_version')!=view['view_id']:
  raise ValueError('固定版本的日行情发布与字段来源尚未共同确认，不能启动新研究')
 fields=[x['name'] for x in meta.get('fields',[]) if isinstance(x,dict) and isinstance(x.get('name'),str)]
 restriction=plan.get('fieldRestriction') or 'available'
 if restriction not in ('available','ohlcv'):raise ValueError('请选择本任务字段范围')
 return freeze(data_fields=fields,engine_fields=FIELDS,requested_fields=None,rules=plan.get('rules') or {},
  explicit_ohlcv=restriction=='ohlcv',method_identity={'version':METHOD_VERSION,'source_contract':'quant-panel-causal-v1','re_source_policy_sha256':RE_POLICY_SHA256,'bff_code_revision':_CODE_REVISION},
  data_identity={'view_id':view['view_id'],'manifest_sha256':view.get('manifest_sha256'),'datasets':{'daily_bars':(view.get('datasets') or {}).get('daily_bars')},
   'project_id':project['id'],'org_id':org,'universe':cfg.get('researchUniverseSymbols') or cfg.get('universe'),
   'development':[plan.get('developmentStart'),plan.get('developmentEnd')],
   'validation':[plan.get('validationStart'),plan.get('validationEnd')],'warmup_sessions':0})

def project_contract(project):
 return ((project.get('config') or {}).get('researchPlan') or {}).get('researchContract')

def check_project(project, source=None, entry=None):
 contract=project_contract(project)
 if not contract:return None # Legacy records retain their original meaning.
 cfg=project['config'];plan=cfg.get('researchPlan') or {};identity=contract['data_identity']
 check_fields([],contract)
 frozen_code=contract.get('method_identity',{}).get('bff_code_revision')
 if frozen_code:
  from .provenance import _CODE_REVISION
  if frozen_code!=_CODE_REVISION:raise ValueError('原研究方法代码版本已变化，不能悄悄替换运行；原证据仍保留')
 if project.get('id') and identity.get('project_id')!=project['id']:raise ValueError('研究契约不属于此工程')
 if fingerprint(plan.get('rules') or {})!=contract['rules_hash']:raise ValueError('预登记方向和门槛已冻结，修改需建立明确的新研究计划')
 expected={'universe':cfg.get('researchUniverseSymbols') or cfg.get('universe'),
  'development':[plan.get('developmentStart'),plan.get('developmentEnd')],
  'validation':[plan.get('validationStart'),plan.get('validationEnd')]}
 if any(identity.get(k)!=v for k,v in expected.items()):raise ValueError('研究数据范围已冻结，未采用更改后的范围')
 if source is not None:
  from .source_contract import inspect_source
  check_fields(inspect_source(source,entry)['fields'],contract)
 return contract


def guard_generic_project_write(connection, uid, project_id, config):
 """The generic personal endpoint cannot replace an institutional workbench.

 Uses the same actor lock as create_topic so creation/write races cannot strip
 the newly frozen server contract. The personal route remains available when
 there is no institutional topic (including deployments without this schema).
 """
 import copy
 connection.execute('SELECT pg_advisory_xact_lock(%s,%s)',(9106,uid))
 table=connection.execute("SELECT to_regclass('quant_factor_topics') AS table_name").fetchone()
 if table and table.get('table_name'):
  topic=connection.execute('SELECT id FROM quant_factor_topics WHERE user_id=%s AND project_id=%s LIMIT 1',(uid,project_id)).fetchone()
  if topic:raise ValueError('机构研究任务请从已确认分支的机构工作台保存；通用工程入口不能替换冻结契约或控制版本')
 clean=copy.deepcopy(config)
 if isinstance(clean.get('researchPlan'),dict):clean['researchPlan'].pop('researchContract',None)
 return clean
