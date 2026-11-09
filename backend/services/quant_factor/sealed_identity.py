"""Recompute the expected heldout spec using the actual isolated RE pure factory."""
from .causality import _run_worker
from .policy import digest,WorkflowError

def expected_identity(request,development_result):
 meta=(development_result or {}).get('meta') or {}
 if not meta.get('data_release_id') or not meta.get('factor_source_hash'):raise WorkflowError('研发证据缺少固定数据或源码身份，不能封存')
 try:receipt=_run_worker({'mode':'spec_identity','request':request,'expected':{k:meta[k] for k in ('data_release_id','factor_source_hash')}})
 except ValueError as exc:raise WorkflowError(str(exc)) from exc
 if receipt.get('request_hash')!=digest(request):raise WorkflowError('封存规格检查与冻结请求不一致')
 return receipt
