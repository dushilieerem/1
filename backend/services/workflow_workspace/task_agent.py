"""Step-scoped assistant; uses the same revision checks and tools as the human UI."""
import json
from .agent import Agent,tool,STR,NUM,INT
from .tasks import ResearchTasks,STAGES
from .store import uid,now,DEFAULT_METHOD

class TaskAgent(Agent):
    def start(self,body):
        if not body.get('task_id'):return super().start(body)
        if not self.key:raise ValueError('请先配置真实模型连接；不会用脚本回复代替 AI')
        tasks=ResearchTasks(self.workspace);t=tasks.get(body['task_id'])
        stage=body.get('stage');intent=body.get('intent')
        if type(stage) is not int or not 0<=stage<6 or intent not in ('task_fill','task_stage'):raise ValueError('无效的步骤或助手操作')
        if body.get('revision')!=t['revision']:raise ValueError('任务版本已变化，请先刷新')
        message=str(body.get('message','')).strip()
        if not 3<=len(message)<=2000:raise ValueError('请输入 3–2000 字的任务说明')
        if intent=='task_fill' and not STAGES[t['module']][stage]:raise ValueError('当前步骤是结果复核，没有可填写的字段')
        with self.lock,self.store.lock:
            if any(a['status'] in ('queued','running') for a in self.store.list('agent')):raise ValueError('已有助手任务在运行')
            tasks._ready(t,t['revision'])
            a={'id':uid('AI'),'status':'queued','created':now(),'task_id':t['id'],'task_revision':t['revision'],
               'module':t['module'],'stage':stage,'intent':intent,'message':message,
               'method':self.store.get('method','current') or DEFAULT_METHOD.copy(),
               'model':self.store.get('settings','current')['model'],'steps':[],'run_ids':[],'evidence_ids':[],
               'form_patch':{},'reply':'','activity':'queued','usage':{'calls':0,'tokens':0,'uncertain':0},'trace_version':3}
            self.store.put('agent',a['id'],a);self.pool.submit(self._run_task,a['id']);return a
    def _run_task(self,identity):
        tasks=ResearchTasks(self.workspace)
        with self.store.lock:
            a=self.store.get('agent',identity)
            if a['status']=='cancelled':return
            a.update(status='running',started=now());self.store.put('agent',identity,a)
        try:
            t=tasks.get(a['task_id']);stage=a['stage'];kind=t['module']
            props={}
            for k in STAGES[kind][stage]:
                if k in ('horizon','groups','rebalance','top_n'):props[k]=INT
                elif k=='cost_bps':props[k]=NUM
                elif k in ('factors','strategies'):
                    props[k]={'type':'array','maxItems':6,'items':{'type':'object','properties':{'id':STR,'weight':NUM},'required':['id','weight'],'additionalProperties':False}}
                elif k=='preprocess':props[k]={'type':'string','enum':['none','zscore','winsor_zscore']}
                else:props[k]=STR
            allowed=[]
            if props:
                allowed.append(tool('fill_current_step','返回当前步骤字段建议；填表模式仅产生草稿，执行模式会保存新版本',props,[]))
            if kind=='factor' and stage==1:allowed.append(tool('validate_expression','校验受限因子表达式',{'expression':STR},['expression']))
            if a['intent']=='task_stage':
                allowed.append(tool('read_report','读取已完成实验证据，不能虚构结果',{'run_id':STR},['run_id']))
                if stage=={'factor':2,'strategy':3,'portfolio':2}[kind]:
                    allowed.append(tool('execute_research','按当前冻结任务参数调用真实计算工具；不会审批',{},[]))
                if stage==4:
                    allowed.append(tool('submit_candidate','仅将通过筛选的当前版本送人工审核；不是批准',{'run_id':STR,'note':STR},['run_id','note']))
            allowed_names={x['function']['name'] for x in allowed}
            if not allowed:raise ValueError('当前步骤没有可执行的助手工具')
            with self.store.lock:
                a=self.store.get('agent',identity);a['allowed_tools']=sorted(allowed_names);self.store.put('agent',identity,a)
            assets=tasks.assets()
            context={'task':t,'current_step':stage+1,'assets':[{k:r.get(k) for k in ('id','kind','name','summary','review','expression')} for r in assets[:20]],
                     'limits':self.workspace.capabilities(),'screen_policy':tasks.state()['policy']}
            system=('你是 Sunvalley 量化研究助手。用户和你使用同一套后端工具。只处理当前步骤，最多4次工具调用、1次实验。'
                    '不能虚构收益或IC，不能审批、修改预算或交易。填表模式仅返回字段建议，用户采纳才保存；执行模式可保存当前步骤或执行已授权计算。'
                    '不能把研发分段对照称为独立留出验证；不能把因子分层前瞻收益称为交易净值。已存在的研究资产可供探索，不代表已审核。'
                    '所有度量必须取自工具返回。不能从名称推断两个资产同式。不得为了通过门槛而反复优化已查看的对照样本或降低阈值；提出新的假设时须提示试验选择偏差。工具失败须如实说明。调用完工具后简要解释结果和下一步。'
                    '\n模式：'+a['intent']+'\n研究方法：'+a['method']['prompt'])
            messages=[{'role':'system','content':system},{'role':'user','content':json.dumps(context,ensure_ascii=False)+'\n用户任务：'+a['message']}]
            calls_used=0;computed=False;revision=t['revision']
            for turn in range(5):
                self._check(identity)
                step=self._step(identity,'model','模型选择当前步骤工具',{'round':turn+1},status='running')
                message=self._completion(messages,allowed,identity)
                calls=message.get('tool_calls') or []
                self._finish_step(identity,step,'completed',selected_tools=[c.get('function',{}).get('name') for c in calls])
                messages.append({k:v for k,v in message.items() if k in ('role','content','tool_calls','reasoning_content')})
                if not calls:
                    self._check(identity)
                    with self.store.lock:
                        a=self.store.get('agent',identity);a.update(status='completed',reply=str(message.get('content') or '请查看工具记录。'),finished=now(),activity='completed')
                        self.store.put('agent',identity,a)
                    return
                for call in calls:
                    self._check(identity);calls_used+=1;name=call.get('function',{}).get('name');step=None
                    try:
                        if calls_used>4:raise ValueError('已达到本轮工具调用上限，请总结已有结果')
                        if name not in allowed_names:raise ValueError('此步骤未授权该工具')
                        args=json.loads(call['function']['arguments'])
                        if not isinstance(args,dict):raise ValueError('工具参数必须是对象')
                        step=self._step(identity,'tool','调用 '+name,args,tool=name,status='running')
                        if name=='fill_current_step':
                            current=tasks.get(t['id'])
                            if current['revision']!=revision:raise ValueError('任务已被更新，不能覆盖；请重试')
                            patch=tasks.patch_for_stage(current,stage,args)
                            if a['intent']=='task_fill':
                                with self.store.lock:
                                    job=self.store.get('agent',identity);job['form_patch'].update(patch);self.store.put('agent',identity,job)
                                result={'form_patch':patch,'saved':False}
                            else:
                                current=tasks.update(t['id'],revision,patch,'AI',identity);revision=current['revision']
                                result={'task_revision':revision,'saved':True,'inputs':current['inputs']}
                        elif name=='validate_expression':result=self.workspace.validate(args)
                        elif name=='execute_research':
                            if computed:raise ValueError('本轮最多执行一次实验')
                            computed=True;r=tasks.execute(t['id'],revision,'AI',identity)
                            with self.store.lock:
                                job=self.store.get('agent',identity);job['run_ids'].append(r['id']);self.store.put('agent',identity,job)
                            result=self.summary(self.workspace.wait(r['id']))
                        elif name=='read_report':
                            r=self.workspace.report(args['run_id']);result=self.summary(r)
                            result['screen']=tasks.screen(r)
                            with self.store.lock:
                                job=self.store.get('agent',identity);job['evidence_ids'].append(r['id']);self.store.put('agent',identity,job)
                        elif name=='submit_candidate':
                            result=self.summary(tasks.submit(t['id'],revision,args['run_id'],args['note'],'AI'))
                        else:raise ValueError('工具未开放')
                    except (ValueError,KeyError,TypeError) as e:result={'error':str(e)[:600]}
                    status='failed' if result.get('error') or result.get('status') in ('failed','interrupted','cancelled') else 'completed'
                    if step:self._finish_step(identity,step,status)
                    self._step(identity,'observation',str(name)+' 返回证据',result,tool=name,status=status)
                    self._check(identity)
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result,ensure_ascii=False)})
            raise ValueError('达到决策轮数上限；已执行的实验及记录保留')
        except Exception as e:
            message=str(e).replace(self.key,'[redacted]')[:800] if self.key else str(e)[:800]
            self._fail_open_steps(identity,message)
            with self.store.lock:
                a=self.store.get('agent',identity)
                if a['status']!='cancelled':a.update(status='failed',error=message,finished=now(),activity='failed');self.store.put('agent',identity,a)
