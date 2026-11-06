"""Bounded DeepSeek tool execution; same Workspace methods as human requests."""
from __future__ import annotations
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib import request,error
from .store import uid,now,DEFAULT_METHOD

def tool(name,description,properties,required):
    return {'type':'function','function':{'name':name,'description':description,'parameters':{'type':'object','properties':properties,'required':required,'additionalProperties':False}}}
STR={'type':'string'};NUM={'type':'number'};INT={'type':'integer'}
TOOLS=[
 tool('validate_expression','校验因子表达式的语法和可用字段',{'expression':STR},['expression']),
 tool('save_factor','保存真实因子定义，返回 factor_id；不会自动登记入库',{'name':STR,'expression':STR,'reason':STR,'preprocess':{'type':'string','enum':['none','zscore','winsor_zscore']}},['name','expression','reason']),
 tool('run_factor','用真实行情计算因子 IC、分层和研发分段对照',{'factor_id':STR,'data_version':STR,'start':STR,'end':STR,'horizon':INT,'groups':INT},['factor_id','data_version','start','end']),
 tool('run_strategy','从已登记因子库构建策略并调用已有回测工具',{'name':STR,'data_version':STR,'start':STR,'end':STR,'rebalance':INT,'top_n':INT,'cost_bps':NUM,'factors':{'type':'array','items':{'type':'object','properties':{'id':STR,'weight':NUM},'required':['id','weight'],'additionalProperties':False}}},['name','data_version','start','end','factors']),
 tool('read_report','读取已有真实实验的摘要和检查结果',{'run_id':STR},['run_id']),
 tool('submit_review','将没有硬检查失败的真实研究结果提交人工审查；不能审批',{'run_id':STR,'reason':STR},['run_id','reason'])
]

FORM_FIELDS={
 ('factor','start'):{'name':STR,'reason':STR},
 ('factor','design'):{'name':STR,'expression':STR,'preprocess':{'type':'string','enum':['none','zscore','winsor_zscore']}},
 ('factor','test'):{'data_version':STR,'start':STR,'end':STR,'horizon':INT,'groups':INT},
 ('strategy','goal'):{'name':STR,'goal':STR},
 ('strategy','rules'):{'rebalance':INT,'top_n':INT,'cost_bps':NUM},
}
STAGE_TOOLS={
 ('factor','design'):{'validate_expression','save_factor'},
 ('factor','test'):{'validate_expression','save_factor','run_factor','read_report'},
 ('factor','results'):{'read_report'},
 ('strategy','backtest'):{'run_strategy','read_report'},
}
def validate_form_patch(module,stage,patch):
    fields=FORM_FIELDS.get((module,stage))
    if not fields or not isinstance(patch,dict) or not patch or set(patch)-set(fields):
        raise ValueError('只能填写当前环节允许的表单字段')
    for key,value in patch.items():
        spec=fields[key];kind=spec['type']
        if kind=='string' and (not isinstance(value,str) or len(value)>2000):raise ValueError('表单文本不合法')
        if kind=='integer' and type(value) is not int:raise ValueError('表单字段须为整数')
        if kind=='number' and (type(value) not in (int,float) or not __import__('math').isfinite(value)):raise ValueError('表单字段须为有限数字')
        if 'enum' in spec and value not in spec['enum']:raise ValueError('表单选项不合法')
        bounds={'horizon':(1,20),'groups':(2,5),'rebalance':(1,60),'top_n':(1,60),'cost_bps':(0,200)}
        if key in bounds and not bounds[key][0]<=value<=bounds[key][1]:raise ValueError('表单参数超出范围')
    return patch

class Agent:
    def __init__(self,workspace,key=''):
        self.workspace=workspace;self.store=workspace.store;self.key=key or os.environ.get('DEEPSEEK_API_KEY','');self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='research-assistant');self.lock=threading.RLock()
    def status(self):return {'configured':bool(self.key),'provider':'DeepSeek','endpoint':'https://api.deepseek.com','usage':self.store.get('settings','current')}
    def configure(self,body):
        with self.lock:
            if any(a['status'] in ('queued','running') for a in self.store.list('agent')):raise ValueError('助手正在运行，请完成后再修改连接')
            key=str(body.get('api_key','')).strip()
            if key:
                if len(key)<15 or '\n' in key:raise ValueError('密钥格式不正确')
                self.key=key
            s=self.store.get('settings','current')
            model=str(body.get('model',s['model'])).strip()
            if not model or len(model)>80:raise ValueError('模型名不合法')
            limit=body.get('token_limit',s['token_limit'])
            if type(limit) is not int or not s['tokens']+s['reserved']+s['uncertain']<=limit<=200000:raise ValueError('本版累计额度不能低于已用/预留量，且不得超过已授权的 200,000 Tokens')
            s.update(model=model,token_limit=limit);self.store.put('settings','current',s)
            return self.status()
    def start(self,body):
        goal=str(body.get('message','')).strip()
        if not 3<=len(goal)<=2000:raise ValueError('请填写 3–2000 字的研究任务')
        form_mode=body.get('intent')=='fill_form'
        stage=str(body.get('stage',''))
        stage_mode=body.get('intent')=='stage'
        if stage_mode and (body.get('module'),stage) not in STAGE_TOOLS:raise ValueError('当前环节未开放 AI 执行')
        form=body.get('form',{})
        if form_mode and (body.get('module'),stage) not in FORM_FIELDS:raise ValueError('当前环节未开放 AI 填表')
        if not isinstance(form,dict) or len(json.dumps(form))>12000:raise ValueError('表单上下文不合法')
        if not self.key:raise ValueError('请先配置真实模型连接；不会用脚本回复代替 AI')
        with self.lock:
            if any(a['status'] in ('queued','running') for a in self.store.list('agent')):raise ValueError('已有助手任务在运行')
            method=self.store.get('method','current') or DEFAULT_METHOD.copy()
            job={'id':uid('AI'),'status':'queued','created':now(),'message':goal,'module':body.get('module','factor'),'method':method,'steps':[],'run_ids':[],'evidence_ids':[],'reply':'','intent':'fill_form' if form_mode else ('stage' if stage_mode else 'research'),'stage':stage,'form':form,'form_patch':{},'trace_version':2,'factor_ids':[],
                 'model':self.store.get('settings','current')['model'],'activity':'queued',
                 'usage':{'calls':0,'tokens':0,'uncertain':0}}
            self.store.put('agent',job['id'],job);self.pool.submit(self._run,job['id']);return job
    def cancel(self,identity):
        with self.store.lock:
            a=self.store.get('agent',identity)
            if not a or a['status'] not in ('queued','running'):raise ValueError('任务不可取消')
            a.update(status='cancelled',finished=now(),activity='cancelled');self.store.put('agent',identity,a)
            self._step(identity,'control','人工停止后续调用；已发出的请求可能仍会完成',status='completed')
            for run_id in a['run_ids']:
                r=self.store.get('run',run_id)
                if r and r['status'] in ('queued','running'):self.workspace.cancel(run_id)
        return a
    def _check(self,identity):
        if self.store.get('agent',identity)['status']=='cancelled':raise ValueError('用户已取消助手任务')
    def _step(self,identity,kind,text,detail=None,**metadata):
        with self.store.lock:
            a=self.store.get('agent',identity)
            step={'id':uid('STEP'),'seq':len(a['steps'])+1,'at':now(),'kind':kind,'text':text,'detail':detail,**metadata}
            a['steps'].append(step)
            if a['status'] in ('queued','running'):a['activity']=kind
            self.store.put('agent',identity,a)
            return step['id']
    def _finish_step(self,identity,step_id,status,**metadata):
        with self.store.lock:
            a=self.store.get('agent',identity)
            step=next(s for s in a['steps'] if s.get('id')==step_id)
            step.update(status=status,finished=now(),**metadata)
            step['duration_ms']=round((step['finished']-step['at'])*1000)
            self.store.put('agent',identity,a)
    def _fail_open_steps(self,identity,error):
        with self.store.lock:
            a=self.store.get('agent',identity)
            for step in a['steps']:
                if step.get('status')=='running':
                    step.update(status='cancelled' if a['status']=='cancelled' else 'failed',finished=now(),error=error)
                    step['duration_ms']=round((step['finished']-step['at'])*1000)
            self.store.put('agent',identity,a)
    def _completion(self,messages,tools,identity):
        self._check(identity)
        s=self.store.get('settings','current')
        payload={'model':s['model'],'messages':messages,'tools':tools,'max_tokens':1100,'temperature':.2}
        encoded=json.dumps(payload,ensure_ascii=False).encode()
        reserve=len(encoded)+1400
        with self.store.lock:
            s=self.store.get('settings','current')
            if s['tokens']+s['uncertain']+s['reserved']+reserve>s['token_limit']:raise ValueError('本版模型额度不足以安全继续；已产生的研究结果保留')
            s['reserved']+=reserve;s['calls']+=1;self.store.put('settings','current',s)
            job=self.store.get('agent',identity)
            usage=job.setdefault('usage',{'calls':0,'tokens':0,'uncertain':0});usage['calls']+=1
            self.store.put('agent',identity,job)
        req=request.Request('https://api.deepseek.com/chat/completions',data=encoded,headers={'Content-Type':'application/json','Authorization':'Bearer '+self.key})
        class NoRedirect(request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        used=None;uncertain=True
        try:
            with request.build_opener(NoRedirect()).open(req,timeout=90) as r:
                raw=r.read(2000001)
                if len(raw)>2000000:raise ValueError('模型响应超出限制')
                response=json.loads(raw)
            usage=response.get('usage',{}).get('total_tokens')
            if type(usage) is int and usage>=0:used=usage;uncertain=False
            return response['choices'][0]['message']
        except error.HTTPError as e:
            uncertain=e.code>=500
            raise ValueError('模型服务返回 HTTP '+str(e.code)+'；请检查连接或额度，未伪造结果') from None
        except (error.URLError,TimeoutError):raise ValueError('模型请求未确认完成；保守保留本次预留用量') from None
        finally:
            with self.store.lock:
                s=self.store.get('settings','current');s['reserved']=max(0,s['reserved']-reserve)
                if used is not None:s['tokens']+=used
                elif uncertain:s['uncertain']+=reserve
                self.store.put('settings','current',s)
                job=self.store.get('agent',identity);usage=job.setdefault('usage',{'calls':0,'tokens':0,'uncertain':0})
                if used is not None:usage['tokens']+=used
                elif uncertain:usage['uncertain']+=reserve
                self.store.put('agent',identity,job)
    @staticmethod
    def summary(job):
        report=job.get('report',{})
        return {'run_id':job['id'],'status':job['status'],'review':job['review'],'error':job.get('error'),
                **{k:report.get(k) for k in ('summary','checks','data','coverage','labels','quantiles','segments','correlations','positions','limitations')},
                'metric_contract':{'grouping':'每个T日按当日因子值排名分层，Q1因子高值；绝非按未来收益分组。前瞻收益只用于各层的事后评价。','icir':'日IC均值除以样本标准差，未年化；未计算显著性p值，不得自行声称显著。'} if job.get('kind')=='factor' else None,
                'evidence_scope':'完整曲线和因子逐日值保存在报告；这里提供已完成的诊断表。不得把未返回的字段说成没有计算。'}
    def _run(self,identity):
        with self.store.lock:
            a=self.store.get('agent',identity)
            if a['status']=='cancelled':return
            a.update(status='running',started=now(),activity='context');self.store.put('agent',identity,a)
        try:
            context=self.workspace.context()
            context['current_form']=a.get('form',{})
            context['current_stage']=a.get('stage','')
            context['releases']=[{'version':r['version'],'symbols':r['symbols'],'start':r['quality']['start'],'end':r['quality']['end']} for r in context['releases']]
            context['capabilities']={k:context['capabilities'][k] for k in ('fields','functions','preprocess')}
            context['library']=[{k:r.get(k) for k in ('id','kind','name','summary')} for r in context['library'][:8]]
            context['factor_definitions']=[{k:r.get(k) for k in ('id','name','expression','preprocess')} for r in context['factor_definitions'][:6]]
            allowed=[t for t in TOOLS if (a['module']=='strategy' or t['function']['name']!='run_strategy')]
            if a.get('intent')=='stage':allowed=[t for t in TOOLS if t['function']['name'] in STAGE_TOOLS[(a['module'],a['stage'])]]
            if a.get('intent')=='fill_form':
                fields=FORM_FIELDS[(a['module'],a['stage'])]
                allowed=[tool('fill_form','填写当前页面草稿，不保存资产、不运行实验、不提交审批',fields,[])]+[t for t in TOOLS if t['function']['name']=='validate_expression']
                context['current_form']=a.get('form',{})
                context['current_stage']=a['stage']
            allowed_names={t['function']['name'] for t in allowed}
            with self.store.lock:
                job=self.store.get('agent',identity);job['allowed_tools']=sorted(allowed_names);self.store.put('agent',identity,job)
            system='你是量化研究工具助手。用户和你使用同一套工具。只能通过提供的工具计算和读取证据，禁止虚构收益、IC或运行结果。不能审批、改变预算或实盘交易。表达式函数仅 delay/ts_mean/ts_std/ts_min/ts_max/rank/zscore/abs/log；窗口最多252且不能负向位移。最多执行2个研究实验、4次工具调用。完成后简明汇报真实结果与限制，差的结果也保留。没有统计证据不要许诺有效。若用户只问问题，不擅自创建实验。研究结束可以提交人工审核，但不能自己批准。\n当前方法：'+a['method']['prompt']
            if a.get('intent')=='fill_form':system+='\n本次仅填写当前页面表单，必须通过 fill_form 返回建议字段；可先校验表达式。保留用户已填的合理内容。不能声称已计算或已保存。数据版本只能选上下文已有版本，日期须在版本覆盖范围内。'
            messages=[{'role':'system','content':system},{'role':'user','content':'工作区上下文：'+json.dumps(context,ensure_ascii=False)+'\n用户任务：'+a['message']}]
            computations=0;tool_count=0
            for turn in range(5):
                self._check(identity)
                model_step=self._step(identity,'model','请求模型选择下一步动作',{'round':turn+1},status='running')
                message=self._completion(messages,allowed,identity)
                self._finish_step(identity,model_step,'completed',selected_tools=[c.get('function',{}).get('name','未知工具') for c in (message.get('tool_calls') or [])])
                messages.append({k:v for k,v in message.items() if k in ('role','content','tool_calls','reasoning_content')})
                calls=message.get('tool_calls') or []
                if not calls:
                    reply=str(message.get('content') or '本轮模型未给出结论，请查看执行记录。')
                    self._check(identity)
                    with self.store.lock:
                        a=self.store.get('agent',identity);a.update(status='completed',reply=reply,finished=now(),activity='completed');self.store.put('agent',identity,a)
                    return
                for call in calls:
                    self._check(identity);name=call['function']['name'];tool_count+=1
                    tool_step=None
                    try:
                        if tool_count>4:raise ValueError('已达本轮工具调用上限；请总结已有结果')
                        if name not in allowed_names:raise ValueError('此研究模块未授权该工具')
                        args=json.loads(call['function']['arguments'])
                        if not isinstance(args,dict):raise ValueError('工具参数须为对象')
                        tool_step=self._step(identity,'tool','调用 '+name,args,tool=name,call_id=call['id'],status='running')
                        if name=='fill_form':
                            patch=validate_form_patch(a['module'],a['stage'],args)
                            if 'expression' in patch:self.workspace.validate({'expression':patch['expression']})
                            with self.store.lock:
                                job=self.store.get('agent',identity);job['form_patch'].update(patch);self.store.put('agent',identity,job)
                            result={'form_patch':patch,'saved':False,'executed':False}
                        elif name=='validate_expression':result=self.workspace.validate(args)
                        elif name=='save_factor':
                            result=self.workspace.save_factor(args,'AI');result={'factor_id':result['id'],'name':result['name'],'expression':result['expression']}
                            with self.store.lock:
                                job=self.store.get('agent',identity);job.setdefault('factor_ids',[]).append(result['factor_id']);self.store.put('agent',identity,job)
                        elif name in ('run_factor','run_strategy'):
                            if computations>=2:raise ValueError('本轮最多运行两个实验')
                            computations+=1;r=self.workspace.run(name[4:],args,'AI')
                            with self.store.lock:
                                a=self.store.get('agent',identity);a['run_ids'].append(r['id']);a['activity']='compute';self.store.put('agent',identity,a)
                            result=self.summary(self.workspace.wait(r['id']))
                        elif name=='read_report':
                            result=self.summary(self.workspace.report(args['run_id']))
                            with self.store.lock:
                                a=self.store.get('agent',identity);a.setdefault('evidence_ids',[])
                                if args['run_id'] not in a['evidence_ids']:a['evidence_ids'].append(args['run_id'])
                                self.store.put('agent',identity,a)
                        elif name=='submit_review':result=self.summary(self.workspace.submit(args['run_id'],args['reason'],'AI'))
                        else:raise ValueError('工具未授权')
                    except (ValueError,KeyError,TypeError) as e:result={'error':str(e)[:600]}
                    result_status='failed' if result.get('error') or result.get('status') in ('failed','interrupted') else ('cancelled' if result.get('status')=='cancelled' else 'completed')
                    if tool_step:self._finish_step(identity,tool_step,result_status)
                    self._step(identity,'observation',name+' 返回结果',result,tool=name,call_id=call['id'],status=result_status)
                    self._check(identity)
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result,ensure_ascii=False)})
            raise ValueError('本轮已到决策上限；真实实验与工具记录已保留，可继续人工处理')
        except Exception as e:
            message=str(e).replace(self.key,'[redacted]')[:800] if self.key else str(e)[:800]
            self._fail_open_steps(identity,message)
            with self.store.lock:
                a=self.store.get('agent',identity)
                if a['status']!='cancelled':a.update(status='failed',error=message,finished=now(),activity='failed');self.store.put('agent',identity,a)
