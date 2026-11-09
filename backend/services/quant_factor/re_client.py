"""Institution factor-only thin RE client. Shared personal/strategy proxy stays unchanged."""
from urllib.parse import urlsplit
from services.core.env_config import env
from services.core.lan_http import request_json
from services.factor import re_factor_async_proxy as common
from .policy import WorkflowError


def base():
 value=str(env('QUANT_FACTOR_RE_BASE',env('QUANT_NOVELTY_RE_BASE','')) or '').rstrip('/')
 parsed=urlsplit(value)
 if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:raise WorkflowError('机构研究计算服务尚未明确配置，未发起计算')
 return value


def headers():
 token=str(env('QUANT_NOVELTY_SERVICE_TOKEN',env('RE_SERVICE_TOKEN','')) or '').strip()
 return {'X-Service-Token':token} if token else None


def target(receipt):
 if not all(isinstance(receipt.get(k),str) and receipt[k] for k in ('service_version','version','method_code_hash','policy_hash')):raise WorkflowError('计算服务的方法身份尚未核对，未发起计算')
 return {'base':base(),'service':'ResearchEngine','service_version':receipt.get('service_version'),'method_version':receipt.get('version'),'method_code_hash':receipt.get('method_code_hash'),'policy_hash':receipt.get('policy_hash')}


def _endpoint(saved=None):
 value=(saved or {}).get('base') or base();parsed=urlsplit(value)
 if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:raise WorkflowError('原计算服务身份无法核对，运行记录保留，不会重发')
 return value+'/api/backtest/factor'


def proxy_submit_factor_backtest(payload,*,target=None):
 body=common._strip_sv(payload)
 try:
  common.validate_execution_timing(body)
  if payload.get('factor_code') is not None:body['factor_code']=common.validated_factor_code(str(payload.get('factor_code') or ''),str(payload.get('factor_name') or 'factor'))
  elif not body.get('library_name'):return 400,{}, {'error':'请选择内置因子或填写因子代码'}
 except ValueError as exc:return 400,{}, {'error':str(exc)}
 status,response_headers,data=request_json(_endpoint(target),method='POST',payload=body,timeout=120,headers=headers())
 return status,response_headers,common._rewrite_poll(data)


def proxy_get_factor_run(run_id,*,target=None):return request_json(_endpoint(target)+'/'+str(run_id).strip(),method='GET',timeout=60,headers=headers())
def proxy_cancel_factor_run(run_id,*,target=None):return request_json(_endpoint(target)+'/'+str(run_id).strip(),method='DELETE',timeout=60,headers=headers())

# Only legacy records without a persisted target use their unchanged historical path.
legacy_get_factor_run=common.proxy_get_factor_run
legacy_cancel_factor_run=common.proxy_cancel_factor_run
