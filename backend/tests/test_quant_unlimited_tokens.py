import copy,json,unittest
from pathlib import Path
from services.quant_factor import token_policy as t,model_budget as b
from services.quant_factor.policy import WorkflowError

class UnlimitedAuthorizationTests(unittest.TestCase):
 def record(self):
  return json.loads((Path(__file__).parents[2]/'institutional-workflow/runtime/verification/pm-cr101-20261110/token-policy-authorization.json').read_text())
 def test_explicit_unlimited_is_not_a_larger_finite_grant(self):
  out=t.validate_authorization(self.record(),261)
  self.assertEqual(out['mode'],'unlimited');self.assertEqual(out['previous_limit_tokens'],100000000)
 def test_missing_limit_null_or_cross_institution_cannot_authorize(self):
  for mutate in [lambda r:r['new_policy'].pop('product_cumulative_token_limit'),lambda r:r['new_policy'].update(product_cumulative_token_limit=1000000000),lambda r:r.update(org_id=262),lambda r:r['supersedes_token_ceiling'].update(historical_records_preserved=False)]:
   record=self.record();mutate(record)
   with self.subTest(record=record['new_policy']),self.assertRaises(WorkflowError):t.validate_authorization(record,261)
 def test_full_provider_total_including_reasoning_is_still_metered(self):
  self.assertEqual(b.measured_usage({'usage':{'prompt_tokens':100,'completion_tokens':16000,'total_tokens':16100}})['total_tokens'],16100)
  self.assertIsNone(b.measured_usage({'content':'partial','usage':{}}))
