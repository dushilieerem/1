"""Real HTTP budget metadata only. Login audit; no model, research or approval action."""
from pathlib import Path
import json,datetime,urllib.request,urllib.error
root=Path(__file__).resolve().parents[4];lines=(root/'institutional-workflow/runtime/coordination/dev-test-accounts.md').read_text().splitlines()
account=next(cells for line in lines if line.strip().startswith('|') and (cells:=[v.strip().strip('`') for v in line.strip().strip('|').split('|')])[0]=='test')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));base='http://127.0.0.1:18799'
def call(path,token=None,body=None):
 headers={'Content-Type':'application/json'}
 if token:headers['Authorization']='Bearer '+token
 try:
  with opener.open(urllib.request.Request(base+path,headers=headers,data=json.dumps(body).encode() if body is not None else None),timeout=10) as r:return r.status,json.load(r)
 except urllib.error.HTTPError as exc:return exc.code,{}
code,auth=call('/api/inst/quant/auth/login',body={'username':account[0],'password':account[1]});assert code==200
path='/api/inst/quant/factor-workflow/model-budget';code,status=call(path,auth['token']);assert code==200 and status['new_authorization']['limit_tokens']==100_000_000 and status['legacy_baseline']=='pending'
anonymous,_=call(path);assert anonymous==401
health_code,health=call('/api/health');assert health_code==200 and health['schema']['head']=='0038_quant_ai_budget'
out={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'transport':'actual18799 HTTP, registered researcher, no auth/data substitutes','path':path,'http_status':code,'budget':status,'anonymous_http_status':anonymous,'schema_head':health['schema']['head'],'auth_login_audit_only':True,'business_model_calls':0,'market_compute_calls':0,'approval_calls':0}
(root/'institutional-workflow/runtime/verification/codex-factor-cr100-budget-20261109/online-budget-readonly.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False))
