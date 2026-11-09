import json,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
import yaml
from services import quant_data_resources as svc

class MetadataTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.home=Path(self.tmp.name);self.view='fixture-v1';self.target=self.home/'views'/self.view/'materialized';self.target.mkdir(parents=True)
  (self.home/'views/current').symlink_to(self.target,target_is_directory=True)
  self.entry={'path':'derived/sample','kind':'derived','release':'r1','sha256':'a'*64,'rows':7,'files':1,'date_min':'2026-01-01','date_max':'2026-01-31','pit_rule':'date <= as_of'}
  self.manifest={'view_id':self.view,'contract_version':'c1','datasets':{'sample':self.entry}}
  self.contract={'contract_version':'c1','datasets':{'sample':{'path':'derived/sample','sha256':'a'*64,'fields':['turnover'],'units':{'turnover':'小数'},'format':'long_partitioned'}}}
  self.monitor={'view_id':self.view,'generated_at':'now','datasets':[{'name':'sample','label':'样例','topic':'行情','fields':[{'name':'turnover','label':'换手率','unit':'百分数'}]}]}
  self.quality={'view_id':self.view,'datasets':{'sample':{'ok':True,'results':[{'id':'structure','ok':True,'message':'结构已检查'}]}}}
  self.definition={'view_id':self.view,'datasets':{'sample':self.entry}}
  (self.target/'derived/sample').mkdir(parents=True);(self.target/'derived/sample/part.parquet').write_bytes(b'fixture only')
  self.write();self.patch=patch.object(svc,'DATA_HOME',self.home);self.patch.start();self.addCleanup(self.patch.stop);svc._VIEW_CACHE.clear()
 def write(self):
  for path,data in [('manifest.json',self.manifest),('data_contract.yaml',self.contract),('view.yaml',self.definition)]:
   (self.target/path).write_text(json.dumps(data) if path.endswith('json') else yaml.safe_dump(data))
  (self.target/'VIEW_ID').write_text(self.view)
  (self.home/'docs').mkdir(exist_ok=True);(self.home/'docs/monitor-data.json').write_text(json.dumps(self.monitor))
  (self.home/'ops/quality').mkdir(parents=True,exist_ok=True);(self.home/'ops/quality'/ (self.view+'.json')).write_text(json.dumps(self.quality))
 def detail(self):return svc.dataset(9,2,'sample',self.view)
 def test_search_index_uses_metadata_units_and_does_not_grant_historical_pit(self):
  d=self.detail();self.assertTrue(d['published']);self.assertEqual(d['fields'][0]['unit'],'小数');self.assertEqual(d['fields'][0]['catalog_unit'],'百分数');self.assertIn('不代表历史',d['pit_label']);self.assertFalse(d['applicability']['is_research_authorization'])
 def test_contract_file_inside_manifest_dataset_directory_is_accepted(self):
  self.contract['datasets']['sample']['path']='derived/sample/part.parquet';self.contract['datasets']['sample']['format']='wide_multiindex';self.write();self.assertEqual(self.detail()['applicability']['evidence_status'],'matched')
 def test_manifest_unknown_dates_are_not_filled_from_monitor(self):
  self.entry['date_min']=None;self.entry['date_max']=None;self.monitor['datasets'][0].update(start='2000-01-01',end='2026-01-31');self.write();d=self.detail();self.assertIsNone(d['start']);self.assertIn('未确认覆盖',d['applicability']['summary'])
 def test_quality_missing_corrupt_wrong_version_and_wrong_schema_differ_from_unchecked(self):
  q=self.home/'ops/quality'/(self.view+'.json')
  for value in [None,'{','[]',json.dumps({'view_id':'other','datasets':{}}),json.dumps({'view_id':self.view,'datasets':{'sample':{'ok':'yes','results':[]}}})]:
   with self.subTest(value=value):
    self.write();q.unlink() if value is None else q.write_text(value);self.assertEqual(self.detail()['quality_status'],'error')
  self.quality['datasets']={};self.write();self.assertEqual(self.detail()['quality_status'],'unchecked')
 def test_unknown_or_path_traversal_view_rejected_and_old_published_view_not_silently_rebased(self):
  for vid in ['../secret','missing']:
   with self.assertRaises(KeyError):svc.dataset(9,2,'sample',vid)
  old=self.home/'views/old/materialized';old.mkdir(parents=True);(old/'VIEW_ID').write_text('old');(old/'manifest.json').write_text('{}')
  with self.assertRaisesRegex(ValueError,'版本已更新'):svc.dataset(9,2,'sample','old')
 def test_external_symlink_is_not_published(self):
  folder=self.target/'derived/sample';(folder/'part.parquet').unlink();folder.rmdir();folder.symlink_to(self.home/'docs',target_is_directory=True);self.assertIsNone(self.detail()['published'])
 def test_fixed_release_symlink_requires_all_manifest_definition_identities(self):
  folder=self.target/'derived/sample';(folder/'part.parquet').unlink();folder.rmdir();source=self.home/'derived/releases/r1/datasets/sample';source.mkdir(parents=True);(source/'part.parquet').write_bytes(b'fixture only');folder.symlink_to(source,target_is_directory=True)
  self.entry['source']=str(source);self.definition['datasets']['sample']={**self.entry,'root':str(self.home/'derived/releases/r1'),'path':'datasets/sample'};self.write();self.assertTrue(self.detail()['published'])
  self.definition['datasets']['sample']['release']='different';self.write();self.assertIsNone(self.detail()['published'])
 def test_catalogue_version_conflict_and_bad_catalog_schema_are_explicit(self):
  self.monitor['view_id']='other';self.write();d=self.detail();self.assertEqual(d['fields'],[]);self.assertIsNone(d['field_count']);self.assertEqual(d['applicability']['evidence_status'],'unknown')
  self.monitor=[];self.write()
  with self.assertRaises(svc.MetadataUnavailable):self.detail()
 def test_schema_bad_contract_does_not_crash_or_claim_applicability(self):
  self.contract=[];self.write();self.assertEqual(self.detail()['applicability']['evidence_status'],'unknown')
 def test_published_quality_denominator_excludes_monitor_only_items(self):
  self.monitor['datasets'].append({'name':'not_released','fields':[]});self.write();c=MagicMock();c.execute.return_value.fetchone.return_value={'n':0};conn=MagicMock();conn.__enter__.return_value=c
  with patch.object(svc,'get_conn',return_value=conn):out=svc.catalogue(9,2)
  self.assertEqual(out['summary']['datasets'],1);self.assertEqual(len(out['datasets']),2);self.assertEqual(out['quality_summary']['total'],1);self.assertEqual(out['datasets'][0]['field_index'][0]['name'],'turnover')

 def test_unknown_contract_format_is_not_claimed_matching(self):
  self.contract['datasets']['sample']['format']='unknown-format';self.write();self.assertEqual(self.detail()['applicability']['evidence_status'],'unknown')
 def test_version_publication_time_is_never_inferred_from_directory_mtime(self):
  first=svc.views(9,2)['views'];self.assertEqual(len(first),1);self.assertIsNone(first[0]['published_at'])
  self.manifest['published_at']='2026-01-31T10:00:00Z';self.write();self.assertEqual(svc.views(9,2)['views'][0]['published_at'],'2026-01-31T10:00:00Z')
