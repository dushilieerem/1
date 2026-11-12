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

TOPIC_BODY={'view_id':'research-rv-1','development_start':'2020-01-01','development_end':'2022-12-31','validation_start':'2023-01-01','validation_end':'2023-12-31','primary_holding_period':1,'policy_version':'v5-p0','max_trials':4}

def test_topic_create_uses_session_identity_and_validates_body():
 with patch('app.routers.quant_factor_workflow._quant_uid',return_value=912),patch('services.quant_factor.ledger.create_topic',return_value={'topic':{'id':'t'}}) as create:
  assert client.post('/api/inst/quant/factor-workflow/projects/p/topics',json={**TOPIC_BODY,'user_id':999}).status_code==422
  assert client.post('/api/inst/quant/factor-workflow/projects/p/topics',json={**TOPIC_BODY,'primary_holding_period':0}).status_code==422
  assert client.post('/api/inst/quant/factor-workflow/projects/p/topics',json=TOPIC_BODY).status_code==200
  create.assert_called_once()
  assert create.call_args.args[:3]==(912,261,'p')

def test_trial_append_rejects_server_derived_fields_and_passes_valid_body():
 body={'branch_id':'b','implementation_hash':'h','executor':'human','outcome':'passed'}
 with patch('app.routers.quant_factor_workflow._quant_uid',return_value=912),patch('services.quant_factor.ledger.append_trial',return_value={'id':'t'}) as append:
  assert client.post('/api/inst/quant/factor-workflow/topics/t/trials',json={**body,'rerun_of':'x'}).status_code==422
  assert client.post('/api/inst/quant/factor-workflow/topics/t/trials',json={**body,'returned_metrics':True}).status_code==422
  assert client.post('/api/inst/quant/factor-workflow/topics/t/trials',json=body).status_code==200
  append.assert_called_once()
  assert append.call_args.args[:3]==(912,261,'t')

def test_threshold_endpoint_passes_k():
 with patch('app.routers.quant_factor_workflow._quant_uid',return_value=912),patch('services.quant_factor.ledger.threshold_view',return_value={'k':5,'threshold':2.57}) as view:
  assert client.get('/api/inst/quant/factor-workflow/topics/t/threshold?k=5').status_code==200
  view.assert_called_once_with(912,261,'t',5)

def test_reviewer_cannot_read_ledger_or_append_trial():
 app.dependency_overrides[require_quant_user]=lambda:{**ctx,'can_write':False,'can_review':True}
 assert client.get('/api/inst/quant/factor-workflow/topics/t/ledger').status_code==403
 assert client.post('/api/inst/quant/factor-workflow/topics/t/trials',json={'branch_id':'b','implementation_hash':'h','executor':'human','outcome':'passed'}).status_code==403

def test_trial_append_rejects_client_rerun_and_diagnostic_kinds():
 base={'branch_id':'b','implementation_hash':'h','executor':'human','outcome':'passed'}
 with patch('app.routers.quant_factor_workflow._quant_uid',return_value=912):
  for kind in ('rerun','static_check','compile','smoke','sealed_validation','manual_edit'):
   assert client.post('/api/inst/quant/factor-workflow/topics/t/trials',json={**base,'kind':kind}).status_code==422
  assert client.post('/api/inst/quant/factor-workflow/topics/t/trials',json={**base,'outcome':'rerun'}).status_code==422
  for key,value in (('view_id','other'),('release_ids',{'ifind':'x'}),('view_manifest_sha256','x'),('as_of','2020-01-01'),('contract_revision','x'),('release_id','x')):
   assert client.post('/api/inst/quant/factor-workflow/topics/t/trials',json={**base,key:value}).status_code==422

def test_import_requires_manager_and_researcher_is_forbidden():
 with patch('app.routers.quant_factor_workflow._quant_uid',return_value=912),patch('services.quant_factor.imports.sync_existing',return_value={'inserted':1}) as sync:
  assert client.post('/api/inst/quant/factor-workflow/imports/svquant-existing').status_code==403
  app.dependency_overrides[require_quant_user]=lambda:{**ctx,'can_manage':True,'can_write':True,'role':'manager'}
  assert client.post('/api/inst/quant/factor-workflow/imports/svquant-existing').status_code==200
  sync.assert_called_once_with(912,261)

def test_import_summary_allows_researcher():
 with patch('app.routers.quant_factor_workflow._quant_uid',return_value=912),patch('services.quant_factor.imports.summary',return_value={'total':331}) as summary:
  assert client.get('/api/inst/quant/factor-workflow/imports/svquant-existing').status_code==200
  summary.assert_called_once_with(912,261)

def test_import_reference_inventory_is_readable_by_researcher():
 with patch('app.routers.quant_factor_workflow._quant_uid',return_value=912),patch('services.quant_factor.imports.reference_inventory',return_value={'total':331}) as inv:
  assert client.get('/api/inst/quant/factor-workflow/imports/svquant-existing/reference').status_code==200
  inv.assert_called_once_with(912,261)


def test_org_topics_use_session_identity_and_ignore_client_scope():
 with patch('app.routers.quant_factor_workflow._quant_uid',return_value=912),patch('services.quant_factor.ledger.list_org_topics',return_value=[]) as rows:
  assert client.get('/api/inst/quant/factor-workflow/topics?user_id=1&org_id=2').status_code==200
  rows.assert_called_once_with(912,261)

def test_reviewer_cannot_list_org_topics():
 app.dependency_overrides[require_quant_user]=lambda:{**ctx,'can_write':False,'can_review':True}
 assert client.get('/api/inst/quant/factor-workflow/topics').status_code==403
