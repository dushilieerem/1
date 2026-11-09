"""Quant budgeted adapter reuses the existing generation prompt/parser/source checks."""
import time
from ai.router.specs import TaskRequest
from app.routers.ai_factor_generation import _validate,_variables,_check_quant_source,_payload,_REPAIR_HINT
from ai.router.tasks.factor_generation import build_messages,is_request_rejection
from . import model_budget

def generate(uid,org,project_id,job_id,body):
 req=_validate(body);variables=_variables(req);started=time.monotonic()
 first=model_budget.run(uid,org,project_id,'job:'+job_id+':implementation:1','research.generate_factor',variables=variables)
 parsed=_check_quant_source(first.get('data') or {},req);model=str(first.get('model') or '');errors=list(parsed.get('errors') or [])
 if errors and not is_request_rejection(errors):
  repair=build_messages(TaskRequest(variables=variables))+[{'role':'assistant','content':str(first.get('content') or '')},{'role':'user','content':_REPAIR_HINT.format(errors='；'.join(errors))}]
  second=model_budget.run(uid,org,project_id,'job:'+job_id+':implementation:2','research.generate_factor',messages=repair)
  parsed=_check_quant_source(second.get('data') or parsed,req);model=str(second.get('model') or model)
 return _payload(parsed,model,round((time.monotonic()-started)*1000))
