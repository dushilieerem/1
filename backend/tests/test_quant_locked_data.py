"""Identity-only fixtures; no market files, SQL or HTTP."""
import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from services.quant_factor import locked_data as d,resources,novelty
from services.quant_factor.policy import WorkflowError

class FixedDataTests(unittest.TestCase):
 def identity(self):
  file_hash='a'*64;aggregate=hashlib.sha256(f'market_data/daily.parquet:{file_hash}\n'.encode()).hexdigest()
  expected={'view_id':'research-rv-20261106-3','view_manifest_sha256':'b'*64,'daily_release':'release-old','daily_dataset_sha256':aggregate}
  return expected,{'version':d.VERSION,**expected,'verification':'actual_file_sha256','daily_files_sha256':{'market_data/daily.parquet':file_hash},'data_release_id':'actual-release'}
 def test_actual_receipt_must_match_every_frozen_dimension_and_actual_report_release(self):
  expected,receipt=self.identity();request={'frozen_data_view':expected};result={'meta':{'data_release_id':'actual-release','frozen_data_identity':receipt}}
  d.confirm_result(result,request)
  for key in (*d.KEYS,'verification','daily_files_sha256','data_release_id'):
   changed=copy.deepcopy(result);changed['meta']['frozen_data_identity'][key]='wrong'
   with self.subTest(key=key),self.assertRaises(WorkflowError):d.confirm_result(changed,request)
 def test_old_preflight_cannot_silently_accept_fixed_identity_and_echoed_request_is_not_proof(self):
  expected,receipt=self.identity();request={'frozen_data_view':expected}
  trusted={'allowed':True,'service_version':'2','version':'worker','method_code_hash':'hash','policy_hash':'policy'}
  with patch('services.quant_factor.re_client.base',return_value='http://fixture.invalid'),patch.object(resources,'request_json',return_value=(200,{},trusted)):
   out=resources.preflight('factor',request);self.assertFalse(out['allowed'])
  with patch('services.quant_factor.re_client.base',return_value='http://fixture.invalid'),patch.object(resources,'request_json',return_value=(200,{},dict(trusted,frozen_data_identity={**receipt,'verification':'metadata_only'}))):
   self.assertTrue(resources.preflight('factor',request)['allowed'])
 def test_novelty_candidate_uses_exact_verified_development_identity(self):
  expected,receipt=self.identity();development={'meta':{'data_release_id':'actual-release','factor_source_hash':'source','spec_hash':'spec','frozen_data_identity':receipt}}
  snapshot={'request':{'factor_name':'fixed','library_name':'fixture'},'plan':{'developmentStart':'2025-07-01','developmentEnd':'2025-09-30'}}
  refs={'builtins':[{'library_name':'fixture','factor_name':'baseline'}],'owned':[]}
  out=novelty.comparison_request(snapshot,development,refs,{'minPairs':30})
  self.assertEqual(out['candidate']['frozen_data_view'],expected);self.assertNotIn('frozen_data_view',snapshot['request'])
 def test_binding_never_overwrites_another_data_identity_or_original_request(self):
  expected,_=self.identity();request={'factor_name':'x'};bound=d.bind(request,expected)
  self.assertNotIn('frozen_data_view',request);self.assertEqual(bound['frozen_data_view'],expected)
  with self.assertRaises(WorkflowError):d.bind(bound,{**expected,'view_id':'another'})
