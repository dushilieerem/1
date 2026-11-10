import copy,hashlib,unittest
from unittest.mock import MagicMock,patch
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from app.errors import install_exception_handlers
from app.routers import quant_factor_workflow as routes
from services.quant_factor import library_source as source

CODE="# 原始注释与空行必须保留\n\ndef alpha(self):\n    return self.close  # 原定义\n"
ROW={'id':'import-one','source_library':'主因子库','source_factor_id':'SV01_0001','factor_name':'SV01_0001'}
def response():return {'library_id':1,'library_name':'主因子库','factor_id':'SV01_0001','function_name':'alpha','source_code':CODE,'source_sha256':hashlib.sha256(CODE.encode()).hexdigest(),'source_hash':'b'*64,'source_hash_scope':'factor_id+adapter_version+original_source+tool_module','source_kind':'current_library_definition','execution_validated':False}
def connection(row=ROW):
 c=MagicMock();c.__enter__.return_value=c;c.execute.return_value.fetchone.return_value=row;return c

class SourceTests(unittest.TestCase):
 def test_original_code_and_distinct_hashes_are_returned_without_execution_or_draft_conversion(self):
  c=connection()
  with patch.object(source,'get_conn',return_value=c),patch.object(source.re_client,'base',return_value='http://private-re'),patch.object(source.re_client,'headers',return_value=None),patch.object(source,'request_json',return_value=(200,{},response())) as http:
   out=source.imported_source(7,9,'import-one')
  self.assertEqual(out['source_code'],CODE);self.assertEqual(out['function_name'],'alpha');self.assertNotEqual(out['source_sha256'],out['source_hash']);self.assertFalse(out['execution_validated']);self.assertNotIn('factor_code',out)
  self.assertEqual(c.execute.call_args.args[1],('import-one',9));self.assertEqual(http.call_args.kwargs['method'],'GET');self.assertTrue(http.call_args.args[0].endswith('/SV01_0001/source'))
 def test_wrong_org_or_private_custom_entry_is_rejected_before_upstream(self):
  for row in (None,{**ROW,'source_library':'custom_lib'},{**ROW,'source_library':'../private'},{**ROW,'source_factor_id':'another_user_factor'}):
   with self.subTest(row=row),patch.object(source,'get_conn',return_value=connection(row)),patch.object(source,'request_json') as http:
    with self.assertRaises(source.SourceLookupError) as exc:source.imported_source(7,99,'import-one')
    self.assertEqual(exc.exception.status,404);http.assert_not_called()
 def test_source_hash_library_factor_and_function_identity_mismatches_are_rejected(self):
  for change in ({'library_name':'另一个库'},{'factor_id':'SV01_0002'},{'source_sha256':'a'*64},{'function_name':'another'},{'source_hash':'invalid'}):
   raw={**response(),**change}
   with self.subTest(change=change),patch.object(source,'get_conn',return_value=connection()),patch.object(source.re_client,'base',return_value='http://private-re'),patch.object(source.re_client,'headers',return_value=None),patch.object(source,'request_json',return_value=(200,{},raw)):
    with self.assertRaises(source.SourceLookupError) as exc:source.imported_source(7,9,'import-one')
    self.assertEqual(exc.exception.code,'source_identity_mismatch')
 def test_not_found_empty_and_unavailable_are_distinct(self):
  for upstream,code,status in [((404,{},{}),'source_not_found',404),((409,{}, {'detail':{'code':'source_empty'}}),'source_empty',409),((200,{}, {**response(),'source_code':''}),'source_empty',409),((503,{}, {'detail':'secret path omitted'}),'source_unavailable',503),((504,{},{}),'source_unavailable',503)]:
   with self.subTest(code=code,status=status),patch.object(source,'get_conn',return_value=connection()),patch.object(source.re_client,'base',return_value='http://private-re'),patch.object(source.re_client,'headers',return_value=None),patch.object(source,'request_json',return_value=upstream):
    with self.assertRaises(source.SourceLookupError) as exc:source.imported_source(7,9,'import-one')
    self.assertEqual((exc.exception.code,exc.exception.status),(code,status));self.assertNotIn('secret',str(exc.exception))

class RouteTests(unittest.TestCase):
 def app(self):
  app=FastAPI();app.include_router(routes.router);install_exception_handlers(app);return app
 def test_read_role_uses_real_route_and_only_current_org_identity(self):
  app=self.app();app.dependency_overrides[routes.require_quant_user]=lambda:{'user':{'id':7},'org':{'id':9},'can_write':False}
  with TestClient(app) as client,patch.object(routes,'_quant_uid',return_value=7),patch.object(source,'imported_source',return_value={'source_code':CODE}) as read:
   out=client.get('/api/inst/quant/factor-workflow/imports/import-one/source')
  self.assertEqual(out.status_code,200);self.assertEqual(read.call_args.args,(7,9,'import-one'))
 def test_no_login_is_denied_before_source_lookup(self):
  with TestClient(self.app()) as client,patch.object(source,'imported_source') as read:
   out=client.get('/api/inst/quant/factor-workflow/imports/import-one/source')
  self.assertIn(out.status_code,(401,403));read.assert_not_called()
 def test_typed_failure_survives_real_error_wrapper(self):
  app=self.app();app.dependency_overrides[routes.require_quant_user]=lambda:{'user':{'id':7},'org':{'id':9}}
  with TestClient(app) as client,patch.object(routes,'_quant_uid',return_value=7),patch.object(source,'imported_source',side_effect=source.SourceLookupError(409,'source_empty','该因子暂未提供源码')):
   out=client.get('/api/inst/quant/factor-workflow/imports/import-one/source')
  self.assertEqual(out.status_code,409);self.assertEqual(out.json(),{'code':'source_empty','error':'该因子暂未提供源码'})
