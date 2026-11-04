from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers.quant_factor_workflow import router
from app.deps import require_quant_user
from services.quant_factor.policy import WorkflowError

app=FastAPI();app.include_router(router);client=TestClient(app)
ctx={'org':{'id':261},'user':{'id':912,'username':'cx_test'}}

def setup_function():
 app.dependency_overrides[require_quant_user]=lambda:ctx

def teardown_function():
 app.dependency_overrides.clear()

def test_identity_comes_from_session_not_body():
 with patch('app.routers.quant_factor_workflow._quant_uid',return_value=912),patch('services.quant_factor.service.create',return_value={'id':'c'}) as create:
  r=client.post('/api/inst/quant/factor-workflow/projects/p/candidates',json={'org_id':999,'user_id':999})
  assert r.status_code==202
  create.assert_called_once_with(912,261,'p')

def test_candidate_not_accessible_returns_404():
 with patch('app.routers.quant_factor_workflow._quant_uid',return_value=912),patch('services.quant_factor.service.current',side_effect=KeyError('c')):
  assert client.get('/api/inst/quant/factor-workflow/candidates/c').status_code==404

def test_failed_gate_returns_conflict():
 with patch('app.routers.quant_factor_workflow._quant_uid',return_value=912),patch('services.quant_factor.service.validate',side_effect=WorkflowError('未通过')):
  assert client.post('/api/inst/quant/factor-workflow/candidates/c/validate').status_code==409

def test_approval_cannot_be_faked_from_browser():
 with patch('app.routers.quant_factor_workflow._quant_uid',return_value=912),patch('services.quant_factor.service.current',return_value={'status':'validation_passed'}):
  r=client.post('/api/inst/quant/factor-workflow/candidates/c/submit',json={'approved':True,'sealed':True,'role':'chairman'})
  assert r.status_code==409

def test_archive_rejects_extra_fields():
 assert client.post('/api/inst/quant/factor-workflow/candidates/c/archive',json={'note':'test','approved':True}).status_code==422

def test_unauthenticated_denied():
 app.dependency_overrides.clear()
 assert client.get('/api/inst/quant/factor-workflow/projects/p/candidates').status_code==401
