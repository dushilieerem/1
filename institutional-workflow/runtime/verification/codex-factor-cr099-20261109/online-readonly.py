"""Existing registered researcher, real18799 HTTP. Auth login audit only; no research write."""
from pathlib import Path
import json,urllib.request,urllib.error,datetime
root=Path(__file__).resolve().parents[4];opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));base='http://127.0.0.1:18799'
lines=(root/'institutional-workflow/runtime/coordination/dev-test-accounts.md').read_text().splitlines()
account=next(cells for line in lines if line.strip().startswith('|') and (cells:=[v.strip().strip('`') for v in line.strip().strip('|').split('|')])[0]=='test')
def api(path,token=None,body=None):
 headers={'Content-Type':'application/json'}
 if token:headers['Authorization']='Bearer '+token
 request=urllib.request.Request(base+path,headers=headers,data=json.dumps(body).encode() if body is not None else None)
 try:
  with opener.open(request,timeout=12) as r:return r.status,json.load(r)
 except urllib.error.HTTPError as e:return e.code,{}
code,auth=api('/api/inst/quant/auth/login',body={'username':account[0],'password':account[1]});assert code==200;token=auth['token'];out={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'transport':'actual HTTP18799, existing registered researcher, no ASGI/auth/data substitutions','auth_login_audit_only':True,'business_writes':0,'model_calls':0,'backtest_calls':0,'approval_calls':0,'checks':[]}
for label,project in [('A','b9d9c387-af10-420e-acb4-a88d831f2265'),('B','ee19ef46-c368-4149-98c0-ccf482789be4')]:
 path='/api/inst/quant/factor-workflow/projects/'+project+'/candidates';code,data=api(path,token);assert code==200
 out['checks'].append({'task':label,'path':path,'status':code,'candidates':[{'id':c['id'],'presentation':c.get('presentation'),'status':c['status']} for c in data['candidates']]})
 path='/api/inst/quant/factor-workflow/projects/'+project+'/workbench';code,data=api(path,token);assert code==200
 out['checks'].append({'task':label,'path':path,'status':code,'branch_id':data['branch_id'],'can_handoff':data['can_handoff'],'has_control_epoch':bool(data.get('control_epoch'))})
code,_=api('/api/inst/quant/factor-workflow/projects/ee19ef46-c368-4149-98c0-ccf482789be4/workbench');assert code==401;out['checks'].append({'anonymous_workbench':code})
(root/'institutional-workflow/runtime/verification/codex-factor-cr099-20261109/online-readonly.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False))
