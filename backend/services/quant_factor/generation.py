"""Quant budgeted adapter reuses the existing generation prompt/parser/source checks."""
import time
from ai.router.specs import TaskRequest
from app.routers.ai_factor_generation import _validate,_variables,_check_quant_source,_payload,_REPAIR_HINT
from ai.router.tasks.factor_generation import build_messages,is_request_rejection
from . import model_budget

def generate(uid,org,project_id,job_id,body,*,research_contract=None,proposal=None,method_snapshot=None):
 task='research.generate_factor'
 if research_contract:
  from .research_method import register_tasks,IMPLEMENTER,validate_snapshot
  validate_snapshot(method_snapshot);register_tasks();task=IMPLEMENTER
 req=_validate(body,max_prompt_chars=12000 if research_contract else 2000);variables=_variables(req);started=time.monotonic()
 first=model_budget.run(uid,org,project_id,'job:'+job_id+':implementation:1',task,variables=variables,method_snapshot=method_snapshot)
 parsed=_check_quant_source(first.get('data') or {},req);model=str(first.get('model') or '');errors=list(parsed.get('errors') or [])
 if errors and not is_request_rejection(errors):
  repair=build_messages(TaskRequest(variables=variables))+[{'role':'assistant','content':str(first.get('content') or '')},{'role':'user','content':_REPAIR_HINT.format(errors='；'.join(errors))}]
  second=model_budget.run(uid,org,project_id,'job:'+job_id+':implementation:2',task,messages=repair,method_snapshot=method_snapshot)
  parsed=_check_quant_source(second.get('data') or parsed,req);model=str(second.get('model') or model)
 result=_payload(parsed,model,round((time.monotonic()-started)*1000))
 if research_contract and result.get('status')=='ready':
  from .source_contract import inspect_source
  from .research_contract import check_fields
  from .policy import WorkflowError
  try:
   factor=result['factor'];actual_fields=inspect_source(factor['factor_code'],factor['factor_name'])['fields'];check_fields(actual_fields,research_contract)
   if proposal and not set(actual_fields)<=set(proposal['required_fields']):raise ValueError('实现使用字段超出已选研究提案：'+', '.join(sorted(set(actual_fields)-set(proposal['required_fields']))))
  except ValueError as exc:raise WorkflowError('实现契约检查未通过：'+str(exc)) from exc
 if research_contract:result['meta']['prompt_version']=method_snapshot['roles'][task]['prompt_version']
 result['research_method']={'version':'bounded-factor-rd-v2','method_snapshot':method_snapshot} if research_contract else None
 return result
