from pathlib import Path
import sys,os
root=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(root/'backend'));os.chdir(root/'backend')
import json,datetime,urllib.request,urllib.error,base64,re
from services.core.env_config import load_env
from services.core.db import get_conn
load_env()
class Response:
 def __init__(self,status,body):self.status_code=status;self.body=body
 def json(self):return json.loads(self.body)
class Client:
 def __init__(self):self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 def request(self,path,headers=None,body=None):
  url=path if path.startswith('http') else 'http://127.0.0.1:18799'+path
  request=urllib.request.Request(url,headers=headers or {},data=None if body is None else json.dumps(body).encode(),method='GET' if body is None else 'POST')
  if body is not None:request.add_header('Content-Type','application/json')
  try:
   with self.opener.open(request,timeout=10) as response:return Response(response.status,response.read())
  except urllib.error.HTTPError as exc:return Response(exc.code,exc.read())
 def get(self,path,headers=None):return self.request(path,headers)
 def post(self,path,json):return self.request(path,body=json)
def value(cell):
 parts=re.findall(r'`([^`]+)`',cell)
 raw=parts[0] if parts else cell.strip()
 if raw.startswith('~/'):
  secret_file=Path(raw).expanduser();assert secret_file.is_file(),'registered credential file missing'
  match=re.search(r'(?im)^\s*password\s*[:=]\s*(.+?)\s*$',secret_file.read_text())
  assert match,'registered credential password field missing'
  return match.group(1).strip()
 return raw
r=Path.cwd().parent;d=r/'institutional-workflow/runtime/verification/codex-factor-closure-20261109';roles={}
for line in (r/'institutional-workflow/runtime/coordination/dev-test-accounts.md').read_text().splitlines():
 if line.startswith('|'):
  fields=[s.strip() for s in line.split('|')[1:-1]]
  if len(fields)==5:
   alias='researcher' if '普通量化研究员' in fields[2] else 'reviewer' if '独立量化复核员' in fields[2] else None
   if alias:roles[alias]=[value(fields[0]),value(fields[1])]
assert set(roles)=={'researcher','reviewer'},'registered roles missing'
checks=[];scope={};c=Client()
for alias,(username,password) in roles.items():
 resp=c.post('/api/inst/quant/auth/login',json={'username':username,'password':password});checks.append({'actor':alias,'path':'/api/inst/quant/auth/login','status':resp.status_code})
 assert resp.status_code==200,'registered '+alias+' login failed (status '+str(resp.status_code)+')'
 identity=resp.json();token=identity['token'];headers={'Authorization':'Bearer '+token};scope[alias]={'org_id':identity['org']['id'],'permission':identity['permissions']['quant'],'product':identity['product']}
 for path in ['/api/inst/quant/me','/api/inst/quant/factor-workflow/assets','/api/inst/quant/factor-workflow/reviews']:
  response=c.get(path,headers=headers);entry={'actor':alias,'path':path,'status':response.status_code};assert response.status_code==200,(alias,path,response.status_code);body=response.json()
  if path.endswith('/assets'):entry['asset_count']=len(body.get('assets',[]))
  if path.endswith('/reviews'):
   items=body.get('candidates',[]);entry['candidate_count']=len(items)
   if items:
    one=c.get('/api/inst/quant/factor-workflow/reviews/'+items[0]['id'],headers=headers);item=one.json() if one.status_code==200 else {}
    checks.append({'actor':alias,'path':'/api/inst/quant/factor-workflow/reviews/{visible_id}','status':one.status_code,'is_author':item.get('is_author',False),'can_claim':item.get('review_actions',{}).get('can_claim',False),'can_decide':item.get('review_actions',{}).get('can_decide',False),'events_exposed':'events' in item});assert one.status_code==200
    if alias=='researcher':assert item.get('is_author') is True and not item.get('review_actions',{}).get('can_decide') and not item.get('review_actions',{}).get('can_claim')
   else:entry['detail_check']='no existing visible review; no fixture created'
  checks.append(entry)
 for path in ['/api/inst/quant/factor-workflow/assets/qfa_not_registered_readonly_probe','/api/inst/quant/factor-workflow/reviews/not_registered_readonly_probe']:
  response=c.get(path,headers=headers);checks.append({'actor':alias,'path':path,'status':response.status_code});assert response.status_code==404
 org=scope[alias]['org_id']
 with get_conn() as conn:
  conn.execute('SET TRANSACTION READ ONLY');conn.execute("SET LOCAL statement_timeout='5s'")
  foreign=conn.execute("SELECT id FROM quant_factor_candidates WHERE org_id<>%s AND archive->'review' IS NOT NULL LIMIT 1",(org,)).fetchone()
  foreign_asset=conn.execute("SELECT archive->'research_asset'->>'id' AS id FROM quant_factor_candidates WHERE org_id<>%s AND archive->>'approved'='true' AND archive->'research_asset'->>'schema'='quant.research-asset.v1' LIMIT 1",(org,)).fetchone()
 for label,row,path in [('foreign_review',foreign,'/api/inst/quant/factor-workflow/reviews/'),('foreign_asset',foreign_asset,'/api/inst/quant/factor-workflow/assets/')]:
  if row:
   response=c.get(path+row['id'],headers=headers);checks.append({'actor':alias,'path':path+'{existing_foreign_id}','status':response.status_code,'check':label});assert response.status_code==404
  else:checks.append({'actor':alias,'check':label,'result':'not available: no existing foreign fixture; no data created'})
 parts=token.split('.')
 if len(parts)==3:
  payload=json.loads(base64.urlsafe_b64decode(parts[1]+'='*(-len(parts[1])%4)));payload['org_id']=int(org)+999999;parts[1]=base64.urlsafe_b64encode(json.dumps(payload,separators=(',',':')).encode()).rstrip(b'=').decode()
  response=c.get('/api/inst/quant/factor-workflow/assets',headers={'Authorization':'Bearer '+'.'.join(parts)});checks.append({'actor':alias,'path':'/api/inst/quant/factor-workflow/assets','check':'tampered_org_claim','status':response.status_code});assert response.status_code==401
for path in ['/api/inst/quant/me','/api/inst/quant/factor-workflow/assets','/api/inst/quant/factor-workflow/reviews','/api/inst/quant/factor-workflow/assets/qfa_not_registered_readonly_probe']:
 response=c.get(path);checks.append({'actor':'anonymous','path':path,'status':response.status_code});assert response.status_code==401
for label,url in [('bff','http://127.0.0.1:18799/api/health'),('frontend','http://127.0.0.1:19536/'),('isolated_re','http://127.0.0.1:18804/api/health')]:
 response=c.get(url);checks.append({'check':'health','surface':label,'status':response.status_code});assert response.status_code==200
result={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'transport':'actual local HTTP to loaded BFF; no dependency substitutes','identities':'registered development researcher and independent reviewer','scope':scope,'checks':checks,'business_mutations':False,'login_only_post':True,'model_calls':0,'backtests':0,'approvals':0,'created_assets':0}
(d/'online-readonly-http.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
