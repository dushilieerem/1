"""Versioned research tasks. No data collection or trading authority."""
from __future__ import annotations
import hashlib
import json
import math
from datetime import date
from .store import uid,now

BOUNDS={'horizon':(1,20),'groups':(2,5),'rebalance':(1,60),'top_n':(1,60),'cost_bps':(0,200)}
FIELDS={
 'factor':{'name','reason','expression','preprocess','data_version','start','end','horizon','groups'},
 'strategy':{'name','reason','data_version','start','end','factors','rebalance','top_n','cost_bps'},
 'portfolio':{'name','reason','strategies'},
}
STAGES={
 'factor':[['name','reason','data_version','start','end'],['expression','preprocess'],['horizon','groups'],[],[],[]],
 'strategy':[['name','reason','data_version','start','end'],['factors'],['rebalance','top_n','cost_bps'],[],[],[]],
 'portfolio':[['name','reason'],['strategies'],[],[],[],[]],
}
POLICY={'version':'research-screen-v1','min_days':60,'min_abs_rank_ic':0.02,'min_coverage':0.8,'min_sharpe':0,'max_drawdown':0.35}
class Conflict(ValueError):pass

class ResearchTasks:
    def __init__(self,workspace):self.ws=workspace;self.store=workspace.store
    def get(self,identity):
        t=self.store.get('task',identity)
        if not t:raise ValueError('研究任务不存在')
        return t
    def _ready(self,t,revision,actor=None):
        if actor and (self.store.get('agent',actor) or {}).get('status') not in ('queued','running'):raise Conflict('助手已停止，不能继续写入任务')
        if type(revision) is not int or t['revision']!=revision:raise Conflict('任务已更新，请刷新后使用当前版本；未覆盖他人修改')
        for a in self.store.list('agent'):
            if a.get('task_id')==t['id'] and a['status'] in ('queued','running') and a.get('intent')=='task_stage' and a['id']!=actor:
                raise Conflict('此任务正在由 AI 执行，请等待或停止助手后再修改')
        if any(r.get('task_id')==t['id'] and r.get('task_revision')==revision and r.get('review')=='pending' for r in self.store.list('run')):
            raise Conflict('当前版本正在送审，请先由审核人退回后再修改')
        if any(r.get('task_id')==t['id'] and r['status'] in ('queued','running') for r in self.store.list('run')):
            raise Conflict('此任务仍在计算；请完成或取消后再操作')
    def _validate(self,kind,inputs):
        if not isinstance(inputs,dict) or set(inputs)-FIELDS[kind]:raise ValueError('包含当前模块不允许的字段')
        for k,v in inputs.items():
            if k in BOUNDS:
                lo,hi=BOUNDS[k]
                if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi or (k!='cost_bps' and type(v) is not int):
                    raise ValueError(f'{k} 须在 {lo}–{hi} 范围内'+('且为整数' if k!='cost_bps' else ''))
            elif k in ('factors','strategies'):
                if not isinstance(v,list) or len(v)>6:raise ValueError('最多选择 6 个研究资产')
                seen=set()
                for item in v:
                    if not isinstance(item,dict) or set(item)!={'id','weight'}:raise ValueError('资产必须包含 id 和 weight')
                    w=item['weight']
                    if not isinstance(item['id'],str) or item['id'] in seen or type(w) not in (int,float) or not math.isfinite(w) or not 0<w<=1:
                        raise ValueError('资产须唯一，权重大于 0 且不超过 1')
                    seen.add(item['id'])
                if k=='strategies' and sum(x['weight'] for x in v)>1+1e-10:raise ValueError('策略资金权重之和不能超过 100%')
            else:
                if not isinstance(v,str) or len(v)>(2000 if k in ('reason','expression') else 120):raise ValueError('文本长度或类型不合法')
                if k=='name' and not v.strip():raise ValueError('请输入任务名称')
                if k in ('start','end'):
                    try:date.fromisoformat(v)
                    except ValueError:raise ValueError('日期格式应为 YYYY-MM-DD') from None
                if k=='preprocess' and v not in ('none','zscore','winsor_zscore'):raise ValueError('不支持该预处理')
        if inputs.get('start') and inputs.get('end') and inputs['start']>=inputs['end']:raise ValueError('开始日期必须早于结束日期')
        version=inputs.get('data_version')
        if version:
            release=next((r for r in self.ws.catalog()['releases'] if r['version']==version and r['status']=='published'),None)
            if not release:raise ValueError('数据版本未发布或不存在')
            q=release['quality']
            if inputs.get('start','')<q['start'] or inputs.get('end','')>q['end']:raise ValueError('研究日期须在所选数据版本覆盖范围内')
            if kind=='strategy' and inputs.get('top_n',1)>len(release['symbols']):raise ValueError('持仓数超过所选数据版本证券数')
            if kind=='factor' and inputs.get('groups',2)*2>len(release['symbols']):raise ValueError('每层至少需要两只证券')
        return inputs
    def create(self,body):
        kind=body.get('module')
        if kind not in FIELDS:raise ValueError('当前开放因子、策略和组合研究任务')
        default={'name':{'factor':'新因子研究','strategy':'新策略研究','portfolio':'新组合研究'}[kind],'reason':''}
        if kind!='portfolio':
            release=next((r for r in self.ws.catalog()['releases'] if r['status']=='published'),None)
            if not release:raise ValueError('暂无已发布真实数据，请先导入数据')
            default.update(data_version=release['version'],start=release['quality']['start'],end=release['quality']['end'])
        if kind=='factor':default.update(expression='',preprocess='winsor_zscore',horizon=5,groups=4)
        elif kind=='strategy':default.update(factors=[],rebalance=5,top_n=4,cost_bps=10)
        else:default.update(strategies=[])
        default.update(body.get('inputs',{}));self._validate(kind,default)
        t={'id':uid('TASK'),'module':kind,'inputs':default,'revision':1,'created':now(),'updated':now(),'run_ids':[]}
        self.store.put_many([('task',t['id'],t),('task_version',t['id']+':1',t)])
        self.store.event('创建研究任务',default['name']);return t
    def update(self,identity,revision,patch,source='human',actor=None):
        with self.store.lock:
            t=self.get(identity);self._ready(t,revision,actor)
            if not isinstance(patch,dict) or set(patch)-FIELDS[t['module']]:raise ValueError('任务字段不合法')
            updated=self._validate(t['module'],dict(t['inputs'],**patch))
            if updated==t['inputs']:return t
            t.update(inputs=updated,revision=t['revision']+1,updated=now())
            self.store.put_many([('task',t['id'],t),('task_version',t['id']+':'+str(t['revision']),t)])
            self.store.event('保存任务版本',t['inputs']['name']+' · v'+str(t['revision']),source)
            return t
    def patch_for_stage(self,t,stage,patch):
        if type(stage) is not int or not 0<=stage<6:raise ValueError('流程步骤无效')
        if not isinstance(patch,dict) or not patch or set(patch)-set(STAGES[t['module']][stage]):raise ValueError('AI 只能修改当前步骤的字段')
        self._validate(t['module'],dict(t['inputs'],**patch))
        if patch.get('expression'):self.ws.validate(patch)
        return patch
    def execute(self,identity,revision,source='human',actor=None):
        with self.store.lock:
            t=self.get(identity)
            # Idempotent per revision: retries cannot start duplicate experiments.
            prior=next((r for r in self.store.list('run') if r.get('task_id')==identity and r.get('task_revision')==revision and r['status'] in ('queued','running','completed')),None)
            if t['revision']!=revision:raise Conflict('任务已更新，请刷新后运行当前版本')
            if prior:return prior
            self._ready(t,revision,actor)
            spec=dict(self._validate(t['module'],t['inputs']))
            if t['module']=='factor':
                if not spec.get('expression','').strip():raise ValueError('请先填写因子表达式')
                factor=self.ws.save_factor(spec,source);spec['factor_id']=factor['id']
            elif not spec.get('factors' if t['module']=='strategy' else 'strategies'):raise ValueError('请先选择已有研究资产')
            r=self.ws.run(t['module'],spec,source,research=True,metadata={'task_id':identity,'task_revision':revision})
            t['run_ids'].append(r['id']);t['updated']=now();self.store.put('task',identity,t)
            return r
    def assets(self):
        return [{'id':r['id'],'kind':r['kind'],'name':r['name'],'review':r['review'],'summary':r['report'].get('summary',{}),
                 'report_sha256':r['report_sha256'],'data':r['report'].get('data'),'created':r['created'],
                 'task_id':r.get('task_id'),'task_revision':r.get('task_revision'),'screen':self.screen(r),
                 'purpose':'research_only','expression':r.get('snapshot',{}).get('expression')}
                for r in self.store.list('run') if r['status']=='completed' and not any(c['status']=='fail' for c in r['report'].get('checks',[]))]
    def screen(self,r):
        report=r.get('report',{});s=report.get('summary',{});reasons=[]
        if r['status']!='completed':reasons.append('实验尚未完成')
        if any(c['status']=='fail' for c in report.get('checks',[])):reasons.append('存在硬检查失败')
        def number(value):return type(value) in (int,float) and math.isfinite(value)
        if r['kind']=='factor':
            if not number(s.get('valid_days')) or s['valid_days']<POLICY['min_days']:reasons.append('有效 IC 天数不足 60')
            ic=s.get('rank_ic_mean')
            if not number(ic) or abs(ic)<POLICY['min_abs_rank_ic']:reasons.append('绝对 Rank IC 不足 0.02')
            coverage=report.get('coverage')
            if not number(coverage) or coverage<POLICY['min_coverage']:reasons.append('因子有效覆盖率不足 80%')
            if len(report.get('segments',[]))<2:reasons.append('缺少研发分段证据')
            if number(ic):
                for seg in report.get('segments',[]):
                    val=seg.get('rank_ic_mean')
                    if not number(val) or val*ic<=0:reasons.append('研发分段 Rank IC 方向不一致');break
        else:
            if not number(s.get('observations')) or s['observations']<POLICY['min_days']:reasons.append('收益观察期不足 60 天')
            if not number(s.get('sharpe')) or s['sharpe']<=POLICY['min_sharpe']:reasons.append('扣费后夏普比率未大于 0')
            if not number(s.get('max_drawdown')) or abs(s['max_drawdown'])>POLICY['max_drawdown']:reasons.append('最大回撤超过 35% 或不可计算')
        return {'eligible':not reasons,'reasons':reasons,'policy':POLICY.copy(),'scope':'研发候选筛选，不是显著性证明、独立验证或资金授权'}
    def submit(self,identity,revision,run_id,note,source='human'):
        with self.store.lock:
            t=self.get(identity)
            if t['revision']!=revision:raise Conflict('提交版本已过期')
            r=self.ws.report(run_id)
            if r.get('task_id')!=identity or r.get('task_revision')!=revision:raise ValueError('报告不属于当前任务版本；请重新运行')
            return self.ws.submit(run_id,note,source)
    def state(self):
        runs=self.store.list('run')
        return {'totals':{'tasks':len(self.store.list('task')),'completed':sum(r['status']=='completed' for r in runs),'active_runs':sum(r['status'] in ('queued','running') for r in runs),'active_agents':sum(a['status'] in ('queued','running') for a in self.store.list('agent')),'pending':sum(r['review']=='pending' for r in runs)},'tasks':self.store.list('task'),'assets':self.assets(),'policy':POLICY.copy(),
                'runs':[{k:v for k,v in r.items() if k not in ('report','snapshot')}|{'screen':self.screen(r)} for r in runs[:100]],
                'events':self.store.list('event')[:80],'agents':self.store.list('agent')[:30],
                'connection':self.ws.agent.status(),'method':self.ws.state()['method']}
