from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.errors import install_exception_handlers
from app.routers import quant_factor_workflow as routes
from services.quant_factor import research_advice as advice

app=FastAPI();app.include_router(routes.router);install_exception_handlers(app)
app.dependency_overrides[routes.require_quant_researcher]=lambda:{'user':{'id':9},'org':{'id':2},'can_write':True}
client=TestClient(app)
BODY={'request_key':'stable','run_id':'original-run','branch_id':'h','control_epoch':'epoch','candidate_id':None,'message':'只比较既定向后窗口'}

def test_actual_error_handler_preserves_definitive_rejection_and_never_claims_saved():
 with patch.object(routes,'_quant_uid',return_value=9),patch.object(advice,'submit',side_effect=advice.AdviceRejected('advice_target_changed','当前研究版本已变化，这笔建议未保存。')):
  response=client.post('/api/inst/quant/factor-workflow/topics/t/research-advice',json=BODY)
 assert response.status_code==409
 assert response.json()=={'error':'当前研究版本已变化，这笔建议未保存。','code':'advice_target_changed','saved':False}

def test_current_and_legacy_clients_pass_explicit_run_target_without_widening_identity():
 for body in (BODY,{k:v for k,v in BODY.items() if k!='run_id'}):
  with patch.object(routes,'_quant_uid',return_value=9),patch.object(advice,'submit',return_value={'id':'receipt','status':'pending'}) as submit:
   response=client.post('/api/inst/quant/factor-workflow/topics/t/research-advice',json=body)
  assert response.status_code==200
  assert submit.call_args.args[:3]==(9,2,'t')
  assert submit.call_args.args[3]['run_id']==body.get('run_id')
