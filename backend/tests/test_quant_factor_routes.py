import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers.quant_factor_workflow import router
from app.deps import require_quant_user
from services.quant_factor.policy import WorkflowError

app=FastAPI();app.include_router(router);client=TestClient(app)
ctx={'org':{'id':261},'can_write':True,'can_review':False,'user':{'id':912,'username':'cx_test'}}

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

def test_reviewer_cannot_mutate_researcher_workflow():
 reviewer={**ctx,'can_write':False,'can_review':True}
 app.dependency_overrides[require_quant_user]=lambda:reviewer
 for url in ('projects/p/candidates','projects/p/assistant','candidates/c/validate','candidates/c/cancel','candidates/c/archive','candidates/c/register','candidates/c/review-request'):
  assert client.post('/api/inst/quant/factor-workflow/'+url,json={'note':'x','library_id':1}).status_code==403

def test_researcher_cannot_review_or_list_other_members():
 assert client.get('/api/inst/quant/factor-workflow/reviews').status_code==403
 assert client.post('/api/inst/quant/factor-workflow/reviews/c',json={'note':'x','decision':'research_supported'}).status_code==403

def test_review_rejects_client_identity_and_approval():
 app.dependency_overrides[require_quant_user]=lambda:{**ctx,'can_review':True,'can_write':False}
 r=client.post('/api/inst/quant/factor-workflow/reviews/c',json={'note':'x','decision':'research_supported','reviewer_id':123,'approved':True})
 assert r.status_code==422

def test_review_identity_from_authorized_context():
 app.dependency_overrides[require_quant_user]=lambda:{**ctx,'can_review':True,'can_write':False}
 with patch('app.routers.quant_factor_workflow._quant_uid',return_value=912),patch('services.quant_factor.review.record',return_value={'id':'c'}) as record:
  assert client.post('/api/inst/quant/factor-workflow/reviews/c',json={'note':'x','decision':'needs_revision'}).status_code==200
  record.assert_called_once_with(912,261,'c','needs_revision','x')

def test_self_review_and_unsubmitted_candidates_rejected():
 from services.quant_factor.review import ensure_reviewer
 import pytest
 with pytest.raises(WorkflowError):ensure_reviewer({'user_id':912,'archive':{'review':{}}},912)
 with pytest.raises(KeyError):ensure_reviewer({'user_id':900,'archive':None},912)
 with pytest.raises(KeyError):ensure_reviewer(None,912)

def test_review_claim_uses_authorized_identity():
 app.dependency_overrides[require_quant_user]=lambda:{**ctx,'can_write':False,'can_review':True}
 with patch('app.routers.quant_factor_workflow._quant_uid',return_value=912),patch('services.quant_factor.review.claim',return_value={'id':'c'}) as claim:
  assert client.post('/api/inst/quant/factor-workflow/reviews/c/claim').status_code==200
  claim.assert_called_once_with(912,261,'c')

def test_review_decision_requires_explicit_assignment():
 from services.quant_factor.review import ensure_assigned
 from services.quant_factor.policy import WorkflowError
 for review in ({}, {'status':'requested'}, {'status':'requested','assigned_to':900}):
  with pytest.raises(WorkflowError):ensure_assigned(review,912)
 ensure_assigned({'status':'requested','assigned_to':912},912)

def test_iteration_bound_and_identity_are_server_validated():
 with patch('app.routers.quant_factor_workflow._quant_uid',return_value=912),patch('services.quant_factor.iterations.start',return_value={'id':'i'}) as start:
  assert client.post('/api/inst/quant/factor-workflow/projects/p/iterations',json={'max_rounds':2}).status_code==202
  start.assert_called_once_with(912,261,'p',2)
  for body in [{'max_rounds':0},{'max_rounds':True},{'max_rounds':21},{'max_rounds':2,'approved':True}]:
   assert client.post('/api/inst/quant/factor-workflow/projects/p/iterations',json=body).status_code==422

def test_reviewer_cannot_start_or_pause_iteration():
 app.dependency_overrides[require_quant_user]=lambda:{**ctx,'can_write':False,'can_review':True}
 assert client.post('/api/inst/quant/factor-workflow/projects/p/iterations',json={'max_rounds':2}).status_code==403
 assert client.post('/api/inst/quant/factor-workflow/iterations/i/pause').status_code==403
