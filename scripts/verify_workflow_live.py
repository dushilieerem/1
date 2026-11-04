"""Run a small real-data acceptance chain against the isolated loopback workspace."""
import json,time,urllib.request,urllib.error
from pathlib import Path
BASE='http://127.0.0.1:18796/api/'
def api(path,body=None):
    req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=120) as r:return json.load(r)
def run(task):
    r=api('v3/tasks/run',{'id':task['id'],'revision':task['revision']});deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        r=api('runs/'+r['id'])
        if r['status'] not in ('queued','running'):break
        time.sleep(.5)
    assert r['status']=='completed',r.get('error',r['status'])
    assert r['report_sha256']
    return r
def get_task(name,module,inputs):
    old=next((t for t in api('v3/state')['tasks'] if t['inputs']['name']==name),None)
    return old or api('v3/tasks',{'module':module,'inputs':dict(inputs,name=name)})
catalog=api('catalog')['catalog'];release=next(r for r in catalog['releases'] if r['status']=='published')
shared={'data_version':release['version'],'start':release['quality']['start'],'end':release['quality']['end']}
factor=get_task('联调验收 · 20日动量','factor',dict(shared,expression='close / delay(close, 20) - 1',reason='真实行情功能验收，比较横截面动量；不作为投资推荐。'))
fr=run(factor);print('factor',fr['id'],fr['report']['summary'],flush=True)
strategy=get_task('联调验收 · 动量选股','strategy',dict(shared,factors=[{'id':fr['id'],'weight':1}],reason='复用未审批的因子研究资产验证回测链路。',top_n=4,rebalance=5,cost_bps=10))
sr=run(strategy);print('strategy',sr['id'],sr['report']['summary'],flush=True)
portfolio=get_task('联调验收 · 80%策略与20%现金','portfolio',{'strategies':[{'id':sr['id'],'weight':.8}],'reason':'验证固定权重研究组合及现金保留，不连接资金账户。'})
pr=run(portfolio);print('portfolio',pr['id'],pr['report']['summary'],flush=True)
assert sr['snapshot']['components'][0]['report_sha256']==fr['report_sha256']
assert pr['snapshot']['components'][0]['report_sha256']==sr['report_sha256']
assert api('v3/tasks/run',{'id':factor['id'],'revision':factor['revision']})['id']==fr['id']
state=api('v3/state')
output={'source':'real published Tencent daily market data','release':release['version'],'rows':release['quality']['rows'],'symbols':len(release['symbols']),
        'checks':['factor computation','unreviewed factor reuse','existing PortfolioEngine and MetricEngine','fixed weight portfolio','provenance hashes','idempotent same-version execution'],
        'runs':[{k:r.get(k) for k in ('id','kind','status','task_id','task_revision','report_sha256')}|{'summary':r['report']['summary'],'screen':next(x['screen'] for x in state['runs'] if x['id']==r['id'])} for r in (fr,sr,pr)],
        'limitations':fr['report']['limitations'],'at':time.time(),'model_used':False}
target=Path(__file__).resolve().parents[1]/'institutional-workflow'/'runtime'/'verification';target.mkdir(exist_ok=True)
(target/'live-research.json').write_text(json.dumps(output,ensure_ascii=False,indent=2))
print('REAL_DATA_CHAIN_PASS',flush=True)
