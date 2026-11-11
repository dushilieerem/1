import unittest,uuid
from unittest.mock import MagicMock,patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.errors import install_exception_handlers
from app.routers import quant_factor_workflow as routes
from services.quant_factor import autonomy

BODY={'scope_id':'server-scope','scope_version':1,'direction':'只研究授权字段','request_key':'e125d83d-9ec6-4dd9-8668-53cac53da70c'}
def app(permission='write'):
 a=FastAPI();a.include_router(routes.router);install_exception_handlers(a)
 a.dependency_overrides[routes.require_quant_user]=lambda:{'user':{'id':7},'org':{'id':9},'can_write':permission=='write','can_review':permission=='review'}
 return a

class AutonomyRouteTests(unittest.TestCase):
 def test_enable_uses_authenticated_actor_and_strict_scope_reference(self):
  with TestClient(app()) as c,patch.object(routes,'_quant_uid',return_value=7),patch.object(autonomy,'enable',return_value={'enabled':True}) as enable:
   out=c.post('/api/inst/quant/factor-workflow/autonomy/authorizations',json=BODY)
  self.assertEqual(out.status_code,200);self.assertEqual(enable.call_args.args,(7,9,BODY))
 def test_clients_cannot_supply_research_ranges_authority_hash_or_boolean_versions(self):
  with TestClient(app()) as c,patch.object(autonomy,'enable') as enable:
   for body in ({**BODY,'org_id':99},{**BODY,'universe_snapshot':['x']},{**BODY,'scope_hash':'fake'},{**BODY,'scope_version':True}):
    with self.subTest(body=body):self.assertEqual(c.post('/api/inst/quant/factor-workflow/autonomy/authorizations',json=body).status_code,400)
   enable.assert_not_called()
 def test_reviewer_can_read_but_cannot_enable_or_change_authorization(self):
  with TestClient(app('review')) as c,patch.object(routes,'_quant_uid',return_value=7),patch.object(autonomy,'status',return_value={'enabled':False,'scopes':[]}) as status,patch.object(autonomy,'enable') as enable,patch.object(autonomy,'control') as control:
   self.assertEqual(c.get('/api/inst/quant/factor-workflow/autonomy').status_code,200)
   self.assertEqual(c.post('/api/inst/quant/factor-workflow/autonomy/authorizations',json=BODY).status_code,403)
   self.assertEqual(c.post('/api/inst/quant/factor-workflow/autonomy/authorizations/a/control',json={'enabled':True,'expected_version':1,'request_key':BODY['request_key']}).status_code,403)
   enable.assert_not_called();control.assert_not_called()
 def test_control_context_and_typed_errors_preserve_definitive_failure(self):
  body={'enabled':False,'expected_version':2,'request_key':BODY['request_key']}
  with TestClient(app()) as c,patch.object(routes,'_quant_uid',return_value=7),patch.object(autonomy,'control',side_effect=autonomy.AutonomyError('authorization_changed','状态已变化')) as control:
   out=c.post('/api/inst/quant/factor-workflow/autonomy/authorizations/original/control',json=body)
  self.assertEqual(out.status_code,409);self.assertEqual(out.json(),{'code':'authorization_changed','error':'状态已变化'});self.assertEqual(control.call_args.args,(7,9,'original',body))
 def test_missing_schema_or_feature_does_not_bootstrap_or_create_a_default_grant(self):
  conn=MagicMock();conn.__enter__.return_value=conn;conn.execute.return_value.fetchone.return_value={'available':False}
  with patch.object(autonomy,'get_conn',return_value=conn):out=autonomy.status(7,9)
  self.assertFalse(out['enabled']);self.assertFalse(out['available']);self.assertEqual(out['scopes'],[])
  self.assertEqual(conn.execute.call_count,1);self.assertTrue(conn.execute.call_args.args[0].startswith('SELECT'))
  conn.reset_mock()
  with patch.object(autonomy,'get_conn',return_value=conn),patch.object(autonomy,'installed',return_value=True),patch.object(autonomy,'enabled',return_value=False):
   with self.assertRaises(autonomy.AutonomyError) as exc:autonomy.enable(7,9,BODY)
   self.assertEqual(exc.exception.code,'autonomy_unavailable')
  conn.execute.assert_not_called()
