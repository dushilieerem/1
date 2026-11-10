"""Authorized read-only library source proxy. Never execute or register source."""
import ast
import hashlib
import re
from urllib.parse import quote
from services.core.db import get_conn
from services.core.lan_http import request_json
from . import re_client

class SourceLookupError(Exception):
 def __init__(self,status,code,message):super().__init__(message);self.status=status;self.code=code

def imported_source(uid,org,imported_id):
 with get_conn() as c:
  row=c.execute('SELECT id,source_library,source_factor_id,factor_name FROM quant_factor_imported_factors WHERE id=%s AND org_id=%s',(imported_id,org)).fetchone()
 if not row:raise SourceLookupError(404,'factor_not_found','因子不存在或无权访问')
 library=str(row['source_library'] or '');factor_id=str(row['source_factor_id'] or '')
 if library in ('custom_lib','user_lib') or not library or any(v in library for v in ('/','\\','..')) or not re.fullmatch(r'SV[0-9]{2}_[0-9]+',factor_id):raise SourceLookupError(404,'factor_not_found','这份目录没有可访问的内置因子源码')
 try:
  status,_,data=request_json(re_client.base()+'/api/factors/'+quote(library,safe='')+'/'+quote(factor_id,safe='')+'/source',method='GET',timeout=15,headers=re_client.headers())
 except Exception:raise SourceLookupError(503,'source_unavailable','源码服务暂不可用，请稍后重试') from None
 if status==404:raise SourceLookupError(404,'source_not_found','这份目录暂时找不到对应源码')
 if status==409 and isinstance(data,dict) and isinstance(data.get('detail'),dict) and data['detail'].get('code')=='source_empty':raise SourceLookupError(409,'source_empty','该因子暂未提供源码')
 if status!=200 or not isinstance(data,dict):raise SourceLookupError(503,'source_unavailable','源码服务暂不可用，请稍后重试')
 source=data.get('source_code')
 if not isinstance(source,str) or not source.strip():raise SourceLookupError(409,'source_empty','该因子暂未提供源码')
 if len(source.encode('utf-8'))>1000000:raise SourceLookupError(502,'source_invalid','源码内容未能完整核对，请稍后重试')
 expected=hashlib.sha256(source.encode('utf-8')).hexdigest()
 if data.get('library_name')!=library or data.get('factor_id')!=factor_id or data.get('source_sha256')!=expected or not isinstance(data.get('library_id'),int) or isinstance(data.get('library_id'),bool) or not isinstance(data.get('source_hash'),str) or not re.fullmatch(r'[0-9a-f]{64}',data['source_hash']) or data.get('source_hash_scope')!='factor_id+adapter_version+original_source+tool_module' or data.get('source_kind')!='current_library_definition':raise SourceLookupError(502,'source_identity_mismatch','源码与所选因子的版本身份未能核对，请稍后重试')
 try:
  names=[n.name for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)]
  function_name=names[0] if len(names)==1 else None
 except SyntaxError:function_name=None
 if data.get('function_name')!=function_name:raise SourceLookupError(502,'source_identity_mismatch','源码函数身份未能核对，请稍后重试')
 return {'imported_id':row['id'],'library_id':data['library_id'],'library_name':library,'factor_id':factor_id,'function_name':function_name,'source_code':source,'source_sha256':expected,'source_hash':data['source_hash'],'source_hash_scope':data['source_hash_scope'],'source_kind':'current_library_definition','execution_validated':False}
