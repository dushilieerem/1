import hashlib,importlib.util,json,os,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch
from services.quant_factor.source_contract import inspect_source,validated_quant_code,VERSION
from services.quant_factor.source_compat import RE_POLICY_SHA256
from services.quant_factor.causality import diagnose_source
ROOT=Path(__file__).resolve().parents[2]
MANUAL='def pm_pressure_repair(self):\n    previous_close = self.close.shift(1)\n    daily_return = self.close / previous_close.where(previous_close > 0) - 1\n    price_range = self.high - self.low\n    closing_pressure = (self.close - self.open) / price_range.where(price_range > 0)\n    volume_base = self.volume.rolling(5, min_periods=3).mean()\n    relative_volume = (self.volume / volume_base.where(volume_base > 0)).clip(0.2, 5.0)\n    relative_range = price_range / previous_close.where(previous_close > 0)\n    range_base = relative_range.rolling(5, min_periods=3).mean()\n    reversal = (-daily_return / range_base.where(range_base > 0)).clip(-3.0, 3.0)\n    raw = reversal * (1.0 - closing_pressure) * relative_volume.rank(axis=1, pct=True)\n    return raw.rank(axis=1, pct=True)\n'

class SourceContractTests(unittest.TestCase):
 def test_user_method_name_preserved_and_unsupported_defaults_lag_fields_rejected(self):
  source='def user_named(self): return self.close.rank(axis=1, pct=True)'
  code=validated_quant_code(source,'user_named');self.assertIn('def user_named(self)',code)
  for bad in ['def f(self, window=5): return self.close.shift(window)','def f(self):\n    window=5\n    return self.close.shift(window)','def f(self): return self.up_and_down_status']:
   with self.subTest(source=bad),self.assertRaises(ValueError):inspect_source(bad,'f')
 def test_obvious_future_operations_fail_before_execution(self):
  for expression in ['self.close.rank(pct=True)','self.close / self.close.mean()','self.close.shift(-1)',"self.close.fillna(method='bfill')",'self.close.rolling(5,center=True).mean()']:
   with self.subTest(expr=expression),self.assertRaises(ValueError):inspect_source('def f(self): return '+expression,'f')
 def test_past_windows_and_explicit_cross_section_are_not_blanket_rejected(self):
  for expression in ['self.close.rolling(5).mean().rank(axis=1,pct=True)','self.close.ewm(span=5).mean()','self.close.expanding().mean()','self.close.rolling(5).rank(pct=True)']:
   with self.subTest(expr=expression):self.assertEqual(inspect_source('def f(self): return '+expression,'f')['static_causal_check'],'passed')
 def test_parameter_dependencies_contribute_to_frozen_lookback(self):
  for expression in ['self.close.where(self.close.shift(30)>0)','self.close.add(self.volume.rolling(21).mean())','self.close.clip(lower=self.close.shift(40))']:
   with self.subTest(expr=expression):self.assertGreaterEqual(inspect_source('def f(self): return '+expression,'f')['lookback_sessions'],20)
 def test_actual_isolated_re_policy_accepts_the_exact_wrapped_source(self):
  path=ROOT/'.workspaces/research-engine-r4/app/services/novelty/source.py';self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),RE_POLICY_SHA256)
  spec=importlib.util.spec_from_file_location('isolated_re_source_contract_test',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  code=validated_quant_code(MANUAL,'pm_pressure_repair');self.assertEqual(module.validate_source(code,'pm_pressure_repair'),code)
 def test_current_policy_verification_is_not_skipped_on_a_cached_diagnostic(self):
  with patch('services.quant_factor.causality._diagnose_cached',return_value={'passed':True}) as cached:
   diagnose_source('def f(self): return self.close','f')
   with patch.object(Path,'read_bytes',return_value=b'changed-policy'):
    with self.assertRaisesRegex(ValueError,'支持版本无法核对'):diagnose_source('def f(self): return self.close','f')
   self.assertEqual(cached.call_count,1)
 def test_manual_physical_ohlc_formula_passes_real_panel_and_novelty_hash(self):
  checked=diagnose_source(MANUAL,'pm_pressure_repair');self.assertTrue(checked['diagnostic']['passed']);self.assertEqual(checked['diagnostic']['cutoff_rows'],[560,600]);self.assertTrue(checked['diagnostic']['actual_re_novelty_schema_accepted']);self.assertEqual(checked['diagnostic']['actual_re_source_hash'],checked['contract']['wrapped_source_sha256'])
 def test_real_panel_prefix_check_detects_future_examples_independent_of_static_guard(self):
  environment=os.environ.copy();environment['TMPDIR']=str(ROOT/'institutional-workflow/runtime/causality-tmp')
  for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):environment[key]='1'
  for expression in ['self.close.rank(pct=True)','self.close / self.close.mean()']:
   with self.subTest(expr=expression):
    process=subprocess.run([sys.executable,'-m','services.quant_factor.causality_worker'],input=json.dumps({'source':'def f(self): return '+expression,'entry':'f'}),cwd=ROOT/'backend',env=environment,text=True,capture_output=True,timeout=18)
    self.assertNotEqual(process.returncode,0);self.assertIn('因果性诊断未通过',json.loads(process.stdout)['error'])

 def test_maximum_supported_backward_windows_are_not_rejected_by_short_prefix(self):
  for expression in ['self.close.shift(504)','self.close.rolling(504,min_periods=504).mean()']:
   with self.subTest(expr=expression):self.assertTrue(diagnose_source('def f(self): return '+expression,'f')['diagnostic']['passed'])

 def test_pure_real_re_spec_identity_uses_exact_wrapped_source(self):
  from services.quant_factor.sealed_identity import expected_identity
  from services.quant_factor.policy import digest
  source='def user_entry(self): return self.close.rank(axis=1,pct=True)'
  code=validated_quant_code(source,'user_entry');source_hash=hashlib.sha256(code.encode()).hexdigest()
  req={'factor_name':'user_entry','factor_code':source,'start':'2025-01-01','end':'2025-03-31'}
  result=expected_identity(req,{'meta':{'data_release_id':'fixed-release','factor_source_hash':source_hash}})
  self.assertEqual(result['request_hash'],digest(req));self.assertEqual(result['expected_identity']['factor_source_hash'],source_hash)
  self.assertEqual(len(result['expected_identity']['spec_hash']),64)
  changed=expected_identity({**req,'end':'2025-03-28'},{'meta':{'data_release_id':'fixed-release','factor_source_hash':source_hash}})
  self.assertNotEqual(result['expected_identity']['spec_hash'],changed['expected_identity']['spec_hash'])
