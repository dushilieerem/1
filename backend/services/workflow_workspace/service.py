"""Product-owned task/library/review service. Compute only through RE HTTP."""
from __future__ import annotations
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib import request,error,parse
from .store import Store,uid,now,DEFAULT_METHOD

def rpc(base,path,body=None,timeout=120):
    u=parse.urlparse(base)
    if u.scheme!='http' or u.hostname not in ('localhost','127.0.0.1') or u.username or u.path not in ('','/') or u.query or u.fragment:raise ValueError('仅支持本机研究服务')
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    req=request.Request(base.rstrip('/')+path,data=None if body is None else json.dumps(body,allow_nan=False).encode(),headers={'Content-Type':'application/json'})
    try:
        with request.build_opener(request.ProxyHandler({}),NoRedirect()).open(req,timeout=timeout) as r:
            raw=r.read(16000001)
            if len(raw)>16000000:raise ValueError('计算结果过大')
            return json.loads(raw)
    except error.HTTPError as e:
        try:detail=json.loads(e.read(5000)).get('detail','研究请求失败')
        except ValueError:detail='研究请求失败'
        raise ValueError(str(detail)[:800]) from None
    except (error.URLError,TimeoutError):raise ValueError('研究计算服务暂不可用；未生成研究结果') from None

class Workspace:
    def __init__(self,root,engine_url):
        self.store=Store(root);self.engine_url=engine_url;self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='research-tool');self.agent=None
    def catalog(self):return rpc(self.engine_url,'/catalog',timeout=15)
    def capabilities(self):return rpc(self.engine_url,'/health',timeout=15)['capabilities']
    def state(self):
        runs=self.store.list('run')
        return {'factors':self.store.list('factor'),'runs':[{k:v for k,v in r.items() if k!='report'} for r in runs[:100]],
                'library':self.store.list('library'),'events':self.store.list('event')[:60],
                'agents':self.store.list('agent')[:15],'connection':self.agent.status() if self.agent else {'configured':False},
                'method':self.store.get('method','current') or DEFAULT_METHOD.copy()}
    def validate(self,body):return rpc(self.engine_url,'/tools/validate_expression',{'expression':body.get('expression')})
    def save_factor(self,body,source='human'):
        name=str(body.get('name','')).strip()
        if not 1<=len(name)<=80:raise ValueError('因子名称须为 1–80 字')
        expression=self.validate(body)['normalized']
        record={'id':uid('F'),'name':name,'expression':expression,'reason':str(body.get('reason',''))[:2000],
                'preprocess':body.get('preprocess','none'),'created':now(),'source':source,'parent_id':body.get('parent_id'),'status':'draft'}
        if record['preprocess'] not in ('none','zscore','winsor_zscore'):raise ValueError('无效预处理')
        self.store.put('factor',record['id'],record);self.store.event('保存因子定义',name,source);return record
    def run(self,kind,body,source='human',*,research=False,metadata=None):
        if kind not in ('factor','strategy','portfolio'):raise ValueError('未知实验类型')
        if sum(r['status'] in ('queued','running') for r in self.store.list('run'))>=4:raise ValueError('当前研究队列已满，请等待或取消任务')
        spec=dict(body);name=str(spec.get('name','')).strip()[:80]
        if kind=='factor':
            factor=self.store.get('factor',spec.get('factor_id',''))
            if not factor:raise ValueError('请先保存因子定义')
            spec.update(expression=factor['expression'],preprocess=factor['preprocess']);name=name or factor['name']
        elif kind=='strategy':
            comps=body.get('factors',[])
            if not isinstance(comps,list) or not 1<=len(comps)<=6:raise ValueError('请选择 1–6 个已登记因子')
            spec['components']=[]
            for item in comps:
                asset=self.store.get('library',item.get('id',''))
                run=self.store.get('run',item.get('id','')) if research else None
                if asset and asset['kind']=='factor':run=self.store.get('run',asset['run_id'])
                if not run or run['kind']!='factor' or run['status']!='completed' or any(c['status']=='fail' for c in run['report'].get('checks',[])):raise ValueError('策略输入必须是计算成功且硬检查通过的因子研究资产')
                fixed=run['snapshot']
                spec['components'].append({'asset_id':run['id'],'report_sha256':run['report_sha256'],'expression':fixed['expression'],'preprocess':fixed.get('preprocess','none'),'weight':item.get('weight',1)})
            name=name or '多因子策略研究'
        else:
            spec['components']=[]
            for item in body.get('strategies',[]):
                asset=self.store.get('library',item.get('id',''))
                run=self.store.get('run',item.get('id','')) if research else None
                if asset and asset['kind']=='strategy':run=self.store.get('run',asset['run_id'])
                if not run or run['kind']!='strategy' or run['status']!='completed' or any(c['status']=='fail' for c in run['report'].get('checks',[])):raise ValueError('组合输入必须是计算成功且硬检查通过的策略研究资产')
                spec['components'].append({'run_id':run['id'],'report_sha256':run['report_sha256'],'weight':item.get('weight',0),'returns':run['report']['returns']})
            name=name or '策略组合研究'
        spec.pop('kind',None)
        job={'id':uid('RUN'),'kind':kind,'name':name,'status':'queued','source':source,'created':now(),'snapshot':spec,'review':'not_submitted','logs':[]}
        if metadata:job.update(metadata)
        with self.store.lock:
            if sum(r['status'] in ('queued','running') for r in self.store.list('run'))>=4:raise ValueError('当前研究队列已满，请等待或取消任务')
            self.store.put('run',job['id'],job)
        self.store.event('创建实验',name,source,job['id']);self.pool.submit(self._execute,job['id']);return job
    def _execute(self,identity):
        with self.store.lock:
            job=self.store.get('run',identity)
            if job['status']!='queued':return
            job['status']='running';job['logs'].append({'at':now(),'message':'固定输入，调用 ResearchEngine 实际计算'});self.store.put('run',identity,job)
        try:
            report=rpc(self.engine_url,'/tools/'+job['kind'],job['snapshot'])
            digest=hashlib.sha256(json.dumps(report,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
            with self.store.lock:
                job=self.store.get('run',identity)
                if job['status']=='cancelled':return
                job.update(status='completed',report=report,report_sha256=digest,finished=now())
                job['logs'].append({'at':now(),'message':'计算完成，保存不可变输入快照与结果摘要'})
                self.store.put('run',identity,job);self.store.event('实验完成',job['name'],job['source'],identity)
        except Exception as e:
            with self.store.lock:
                job=self.store.get('run',identity)
                if job['status']=='cancelled':return
                job.update(status='failed',error=str(e)[:800],finished=now());self.store.put('run',identity,job);self.store.event('实验失败',job['error'],job['source'],identity)
    def wait(self,identity,timeout=150):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            job=self.store.get('run',identity)
            if job['status'] not in ('queued','running'):return job
            time.sleep(.2)
        raise ValueError('计算仍在运行，请稍后查看实验记录')
    def report(self,identity):
        job=self.store.get('run',identity)
        if not job:raise ValueError('实验不存在')
        return job
    def cancel(self,identity):
        with self.store.lock:
            job=self.report(identity)
            if job['status'] not in ('queued','running'):raise ValueError('实验当前不可取消')
            job.update(status='cancelled',finished=now());self.store.put('run',identity,job)
            self.store.event('取消实验','已停止接收结果；底层已发起的纯计算可能继续完成','human',identity)
            return job
    def submit(self,identity,note,source='human'):
        with self.store.lock:
            job=self.report(identity)
            if job['status']!='completed':raise ValueError('只有已完成实验能提交审核')
            if job['review'] not in ('not_submitted','returned'):raise ValueError('该实验已提交或已决定')
            if any(c['status']=='fail' for c in job['report'].get('checks',[])):raise ValueError('存在未通过的硬检查，不能送审')
            if job.get('task_id'):
                from .tasks import ResearchTasks
                tasks=ResearchTasks(self);task=tasks.get(job['task_id'])
                if task['revision']!=job['task_revision']:raise ValueError('任务已修改，旧版本报告不能送审当前版本')
                screen=tasks.screen(job)
                if not screen['eligible']:raise ValueError('未达到研发候选筛选条件：'+'；'.join(screen['reasons']))
                job['screen_snapshot']=screen
            if len(str(note).strip())<4:raise ValueError('请填写至少 4 字的提交依据')
            job.update(review='pending',submission={'at':now(),'note':str(note).strip()[:2000],'source':source});self.store.put('run',identity,job)
            self.store.event('提交研究审核',job['name'],source,identity);return job
    def decide(self,identity,decision,note,source='human'):
        if source!='human':raise ValueError('AI 无权登记研究资产或代替人工审批')
        if decision not in ('approve','return','reject') or len(str(note).strip())<4:raise ValueError('请选择决定并填写至少 4 字依据')
        with self.store.lock:
            job=self.report(identity)
            if job['review']!='pending':raise ValueError('当前没有待审版本')
            job.update(review={'approve':'approved','return':'returned','reject':'rejected'}[decision],decision={'at':now(),'note':str(note).strip()[:2000],'actor':'本机研究责任人'})
            writes=[]
            if decision=='approve':
                if any(c['status']=='fail' for c in job['report'].get('checks',[])):raise ValueError('硬检查失败，不能登记入库')
                asset={'id':uid('LIB'),'kind':job['kind'],'name':job['name'],'run_id':identity,'report_sha256':job['report_sha256'],
                       'summary':job['report']['summary'],'created':now(),'purpose':'research_only','status':'registered','expression':job['snapshot'].get('expression')}
                writes.append(('library',asset['id'],asset));job['library_id']=asset['id']
            writes.append(('run',identity,job));self.store.put_many(writes)
            self.store.event('人工研究审核',job['review']+'：'+str(note)[:300],source,identity);return job
    def context(self):
        catalog=self.catalog();published=[r for r in catalog['releases'] if r['status']=='published']
        return {'releases':published[:2],'library':self.store.list('library')[:12],'factor_definitions':self.store.list('factor')[:8],
                'capabilities':self.capabilities(),'recent_runs':[{'id':r['id'],'name':r['name'],'status':r['status'],'review':r['review'],'summary':r.get('report',{}).get('summary'),'error':r.get('error')} for r in self.store.list('run')[:8]]}
    def save_method(self,body):
        prompt=str(body.get('prompt','')).strip()
        if not 10<=len(prompt)<=3000:raise ValueError('方法说明须为 10–3000 字')
        old=self.store.get('method','current');value={'version':(old or {}).get('version',1)+1,'prompt':prompt,'at':now()}
        self.store.put('method','current',value);self.store.event('更新研究助手方法','v'+str(value['version']));return value
