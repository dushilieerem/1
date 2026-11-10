"""Fixed published identity for quant-only development, novelty and heldout requests."""
import copy,hashlib,json
from services.core.db import get_conn
from .policy import WorkflowError
VERSION='quant-frozen-view-v1'
KEYS=('view_id','view_manifest_sha256','daily_release','daily_dataset_sha256')

def _published(view_id,manifest_sha):
 from services.quant_data_resources import _published_view_paths
 path=_published_view_paths().get(view_id)
 if not path:raise WorkflowError('固定数据版本暂不可读取；未改用当前版本')
 try:raw=(path/'manifest.json').read_bytes();manifest=json.loads(raw)
 except (OSError,ValueError):raise WorkflowError('固定数据版本元数据读取失败；未改用当前版本') from None
 if manifest.get('view_id')!=view_id or hashlib.sha256(raw).hexdigest()!=manifest_sha:raise WorkflowError('固定数据版本身份与原计划不一致；原记录保留')
 daily=(manifest.get('datasets') or {}).get('daily_bars')
 if not isinstance(daily,dict) or not daily.get('release') or not daily.get('sha256'):raise WorkflowError('固定版本缺少日行情发布身份')
 return {'view_id':view_id,'view_manifest_sha256':manifest_sha,'daily_release':daily['release'],'daily_dataset_sha256':daily['sha256']}

def for_topic(topic):
 expected=_published(topic.get('view_id'),topic.get('view_manifest_sha256'))
 release=(topic.get('release_ids') or {}).get('daily_bars')
 if release and release!=expected['daily_release']:raise WorkflowError('固定日行情版本与任务原计划不一致')
 return expected

def for_project(uid,org,project_id,*,connection_factory=None):
 with (connection_factory or get_conn)() as c:row=c.execute('SELECT * FROM quant_factor_topics WHERE user_id=%s AND org_id=%s AND project_id=%s',(uid,org,project_id)).fetchone()
 return for_topic(dict(row)) if row else None

def for_config(config):
 contract=((config or {}).get('researchPlan') or {}).get('researchContract')
 if not contract:return None
 from .research_contract import check_fields
 check_fields([],contract)
 identity=contract.get('data_identity') or {};expected=_published(identity.get('view_id'),identity.get('manifest_sha256'))
 daily=(identity.get('datasets') or {}).get('daily_bars') or {}
 if daily.get('release')!=expected['daily_release'] or daily.get('sha256')!=expected['daily_dataset_sha256']:raise WorkflowError('固定字段契约与日行情发布身份不一致')
 return expected

def bind(request,identity):
 out=copy.deepcopy(request)
 if identity:
  if out.get('frozen_data_view') not in (None,identity):raise WorkflowError('计算请求已绑定另一固定数据版本')
  out['frozen_data_view']=dict(identity)
 return out

def verify_receipt(receipt,expected,*,actual):
 if not expected:return
 if not isinstance(receipt,dict) or receipt.get('version')!=VERSION or any(receipt.get(k)!=expected[k] for k in KEYS):raise WorkflowError('计算服务尚未核实本任务的固定数据版本；未采用当前数据替代')
 if receipt.get('verification')!=('actual_file_sha256' if actual else 'metadata_only'):raise WorkflowError('固定数据身份尚未完成所需核验')
 files=receipt.get('daily_files_sha256')
 if not isinstance(files,dict) or not files:raise WorkflowError('固定日行情缺少实际文件身份')
 aggregate=hashlib.sha256()
 for name,value in sorted(files.items()):
  if not isinstance(name,str) or not isinstance(value,str) or len(value)!=64:raise WorkflowError('固定日行情文件身份无效')
  aggregate.update(f'{name}:{value}\n'.encode())
 if aggregate.hexdigest()!=expected['daily_dataset_sha256']:raise WorkflowError('实际日行情文件与原发布指纹不一致')

def confirm_result(result,request):
 expected=request.get('frozen_data_view')
 if not expected:return
 meta=result.get('meta') or {};receipt=meta.get('frozen_data_identity')
 verify_receipt(receipt,expected,actual=True)
 if not meta.get('data_release_id') or receipt.get('data_release_id')!=meta['data_release_id']:raise WorkflowError('实际读取的数据身份与报告不一致')

def from_result(result):
 receipt=(result.get('meta') or {}).get('frozen_data_identity')
 if not isinstance(receipt,dict):raise WorkflowError('研发报告缺少可核验的固定数据身份，不能拼接新计算')
 expected={key:receipt.get(key) for key in KEYS};verify_receipt(receipt,expected,actual=True)
 return expected
