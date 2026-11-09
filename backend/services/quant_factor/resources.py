"""Per-action private RE preflight; no market compute or model invocation."""
import re
from services.core.env_config import env
from services.core.re_config import RE_BASE
from services.core.lan_http import request_json
from .policy import WorkflowError,digest


def static_sample(symbols):
 if not isinstance(symbols,list) or not symbols or len(symbols)>80:raise WorkflowError('固定研究样本须填写1至80个证券代码')
 clean=[str(s).strip().upper() for s in symbols]
 if len(set(clean))!=len(clean) or any(not re.fullmatch(r'[0-9]{6}\.(SZ|SH|BJ)',s) for s in clean):raise WorkflowError('请填写不重复的完整证券代码，如000001.SZ、600000.SH')
 identity=digest({'symbols':clean,'membership_mode':'static'})
 return {'asset_id':'qfs_'+identity[:24],'version':'1','content_hash':identity,'symbols':clean,'membership_mode':'static'}


def scope_request(config):
 plan=config.get('researchPlan') or {};request={'start':plan.get('developmentStart'),'end':plan.get('developmentEnd')}
 if config.get('researchUniverseSymbols'):request['universe_snapshot']=static_sample(config['researchUniverseSymbols'])
 else:request['universe']=config.get('universe') or 'CSI300'
 return request


def preflight(kind,request):
 from .re_client import base as compute_base
 try:base=compute_base()
 except WorkflowError as exc:return {'allowed':False,'reasons':[str(exc)],'candidate_warmup_sessions':0}
 token=env('QUANT_NOVELTY_SERVICE_TOKEN',env('RE_SERVICE_TOKEN','')) or '';headers={'X-Service-Token':token} if token else None
 try:code,_,result=request_json(base+'/api/factor/compute-preflight',method='POST',payload={'kind':kind,'request':request},timeout=10,headers=headers)
 except Exception:return {'allowed':False,'reasons':['受控计算范围目前无法核对，尚未启动计算；请稍后确认'],'candidate_warmup_sessions':0}
 if code!=200 or not isinstance(result,dict) or not isinstance(result.get('allowed'),bool):return {'allowed':False,'reasons':['计算服务尚未提供本次范围的安全预检，尚未启动计算'],'candidate_warmup_sessions':0}
 if result['allowed']:
  from .re_client import target
  try:target(result)
  except WorkflowError as exc:return {**result,'allowed':False,'reasons':[str(exc)]}
 return result


def require(kind,request):
 receipt=preflight(kind,request)
 if not receipt['allowed']:raise WorkflowError('；'.join(receipt.get('reasons') or ['本次计算范围尚未确认']))
 return receipt


def config_preflight(config):
 receipt=preflight('factor',scope_request(config));limit=receipt.get('max_development_trials')
 budget=(config.get('researchPlan') or {}).get('maxTrials')
 if limit is not None and (isinstance(budget,bool) or not isinstance(budget,(int,float)) or budget<1 or budget>limit):
  receipt={**receipt,'allowed':False,'reasons':[*(receipt.get('reasons') or []),'本次受控研究试验预算最多'+str(limit)+'次，请明确填写范围内的预算']}
 return receipt


def require_config(config):
 receipt=config_preflight(config)
 if not receipt['allowed']:raise WorkflowError('；'.join(receipt.get('reasons') or ['本次计算范围尚未确认']))
 return receipt
