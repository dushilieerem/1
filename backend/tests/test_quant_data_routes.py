from unittest.mock import patch
from uuid import UUID
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers.quant_data_resources import router
from app.deps import require_quant_user
from services import quant_data_resources as svc
app=FastAPI();app.include_router(router);client=TestClient(app)
ctx={'org':{'id':261},'user':{'id':912},'can_write':True,'can_review':False}
def setup_function():app.dependency_overrides[require_quant_user]=lambda:ctx
def teardown_function():app.dependency_overrides.clear()
def test_dataset_version_and_session_identity_are_forwarded():
 with patch('app.routers.quant_data_resources._quant_uid',return_value=912),patch.object(svc,'dataset',return_value={'name':'industry_daily'}) as read:
  assert client.get('/api/inst/quant/data-resources/catalog/industry_daily?view_id=fixed&org_id=999').status_code==200
  read.assert_called_once_with(912,261,'industry_daily','fixed')
def test_unknown_view_and_version_conflict_and_unreadable_catalog_are_distinct():
 with patch('app.routers.quant_data_resources._quant_uid',return_value=912):
  with patch.object(svc,'dataset',side_effect=KeyError()):assert client.get('/api/inst/quant/data-resources/catalog/x?view_id=unknown').status_code==404
  with patch.object(svc,'dataset',side_effect=ValueError('版本更新')):assert client.get('/api/inst/quant/data-resources/catalog/x?view_id=old').status_code==409
  with patch.object(svc,'catalogue',side_effect=svc.MetadataUnavailable('目录格式错误')):assert client.get('/api/inst/quant/data-resources/catalog').status_code==503

def test_researcher_usage_remains_member_scoped_and_manager_flag_is_server_derived():
 with patch('app.routers.quant_data_resources._quant_uid',return_value=912),patch.object(svc,'view_usage',return_value={}) as usage:
  assert client.get('/api/inst/quant/data-resources/views/fixed/usage?all_members=true').status_code==200
  usage.assert_called_once_with(912,261,'fixed',False)
def test_request_uuid_supported_but_browser_cannot_supply_actor_or_approval():
 rid='c99c3808-0000-4000-8000-000000000001'
 with patch('app.routers.quant_data_resources._quant_uid',return_value=912),patch.object(svc,'submit_request',return_value={'id':rid}) as create:
  assert client.post('/api/inst/quant/data-resources/requests',json={'title':'fixture','request_id':rid}).status_code==200
  assert create.call_args.args[:2]==(912,261);assert create.call_args.args[2]['request_id']==UUID(rid)
  for body in [{'title':'fixture','request_id':'not-a-uuid'},{'title':'fixture','org_id':999},{'title':'fixture','status':'delivered'}]:assert client.post('/api/inst/quant/data-resources/requests',json=body).status_code==422

def test_researcher_cannot_register_delivery():
 with patch('app.routers.quant_data_resources._quant_uid',return_value=912),patch.object(svc,'update_request') as update:
  assert client.patch('/api/inst/quant/data-resources/requests/x',json={'status':'delivered','delivered_view':'fixed'}).status_code==403
  update.assert_not_called()
def test_readonly_role_cannot_create_request():
 app.dependency_overrides[require_quant_user]=lambda:{**ctx,'can_write':False,'can_review':True}
 assert client.post('/api/inst/quant/data-resources/requests',json={'title':'fixture'}).status_code==403

def test_manager_can_only_call_delivery_with_authorized_identity():
 app.dependency_overrides[require_quant_user]=lambda:{**ctx,'can_manage':True}
 with patch('app.routers.quant_data_resources._quant_uid',return_value=912),patch.object(svc,'update_request',side_effect=ValueError('交付视图不存在或未发布')) as update:
  assert client.patch('/api/inst/quant/data-resources/requests/x',json={'status':'delivered','delivered_view':'not-materialized'}).status_code==409
  assert update.call_args.args[:3]==(912,261,'x')
def test_anonymous_cannot_read_catalog_or_usage_or_requests():
 app.dependency_overrides.clear()
 for path in ['catalog','views/fixed/usage','requests']:assert client.get('/api/inst/quant/data-resources/'+path).status_code==401
