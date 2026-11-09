"""CR097: narrow causal panel source contract for NEW institutional candidates.

Does not rewrite user formulas or change shared personal/strategy validation.
The actual RE policy is frozen and parity-tested; numerical validity wrapper is
added only after causal analysis so its final finite-value any() is not mistaken
for a factor's across-time aggregation.
"""
from __future__ import annotations
import ast,hashlib
from dataclasses import dataclass
from functools import lru_cache
from services.factor.code_validation import validated_factor_code
from .source_compat import validate_source as re_validate_source,RE_POLICY_SHA256
VERSION='quant-panel-causal-v1'
FIELDS=frozenset('open high low close volume amount turnover'.split())
MAX_LOOKBACK=504
AGGREGATES={'sum','mean','std','var','min','max','median','quantile','rank','count','corr','cov'}
@dataclass(frozen=True)
class Info:
 kind:str
 lookback:int|None=0
 value:object=None

def _literal(node,env):
 if isinstance(node,ast.Constant):return node.value
 if isinstance(node,ast.Name):return env.get(node.id,Info('unknown')).value
 if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
  v=_literal(node.operand,env)
  if type(v) in (int,float):return -v if isinstance(node.op,ast.USub) else v
 return None

def _maxlook(items):
 values=[x.lookback for x in items if x.kind in ('matrix','window')]
 return None if any(x is None for x in values) else max(values or [0])

class Analyzer:
 def __init__(self,fn):self.env={};self.fn=fn;self.returns=[]
 def error(self,node,message):raise ValueError('第'+str(getattr(node,'lineno',1))+'行：'+message)
 def axis(self,call):
  for kw in call.keywords:
   if kw.arg=='axis':return _literal(kw.value,self.env)
  if isinstance(call.func,ast.Attribute) and call.func.attr!='quantile' and call.args:return _literal(call.args[0],self.env)
  return None
 def expression(self,node):
  if isinstance(node,ast.Constant):
   if type(node.value) in (int,float) and abs(node.value)>1_000_000:self.error(node,'数值常量超出当前有界实现范围')
   return Info('scalar',value=node.value)
  if isinstance(node,ast.Name):return self.env.get(node.id,Info('scalar' if node.id in ('np','float','int','ValueError') else 'unknown'))
  if isinstance(node,ast.Attribute):
   if isinstance(node.value,ast.Name) and node.value.id=='self':
    if node.attr not in FIELDS:self.error(node,'当前统一计算契约不支持字段 '+node.attr+'，请使用已支持的价量字段')
    return Info('matrix')
   if isinstance(node.value,ast.Name) and node.value.id=='np':return Info('scalar')
   return self.expression(node.value)
  if isinstance(node,(ast.BinOp,ast.Compare,ast.BoolOp,ast.UnaryOp,ast.IfExp)):
   children=[x for x in ast.iter_child_nodes(node) if isinstance(x,ast.expr)];infos=[self.expression(x) for x in children]
   if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Pow):
    power=_literal(node.right,self.env)
    if type(power) not in (int,float) or abs(power)>16:self.error(node,'幂运算只支持明确且绝对值不超过16的固定指数')
   if isinstance(node,ast.BinOp) and any(x.kind=='sequence' for x in infos):self.error(node,'当前契约不支持序列扩展运算')
   return Info('matrix' if any(x.kind=='matrix' for x in infos) else 'scalar',_maxlook(infos))
  if isinstance(node,(ast.List,ast.Tuple,ast.Dict)):
   for child in ast.iter_child_nodes(node):
    if isinstance(child,ast.expr):self.expression(child)
   return Info('sequence')
  if not isinstance(node,ast.Call):self.error(node,'此表达式无法按当前因果性契约确认')
  args=[self.expression(x) for x in node.args];kwargs={kw.arg:kw.value for kw in node.keywords}
  keyword_infos=[self.expression(kw.value) for kw in node.keywords]
  if isinstance(node.func,ast.Name):
   if node.func.id in ('min','max','float','int') and any(x.kind in ('matrix','window') for x in args):self.error(node,'不得将整个时间区间聚合成标量后回填因子值')
   return Info('matrix' if node.func.id=='abs' and any(x.kind=='matrix' for x in args) else 'scalar',_maxlook([*args,*keyword_infos]))
  if isinstance(node.func.value,ast.Name) and node.func.value.id=='np':return Info('matrix' if any(x.kind=='matrix' for x in args) else 'scalar',_maxlook([*args,*keyword_infos]))
  receiver=self.expression(node.func.value);method=node.func.attr
  combined_lookback=_maxlook([receiver,*args,*keyword_infos])
  if method in ('rolling','ewm','expanding'):
   if receiver.kind!='matrix':self.error(node,'窗口操作需要明确的面板输入')
   if method=='rolling':
    window=node.args[0] if node.args else kwargs.get('window');value=_literal(window,self.env) if window else None
    if type(value) is not int or not 1<=value<=MAX_LOOKBACK:self.error(node,'滚动窗口须是1至504的固定向后窗口')
    if 'center' in kwargs and _literal(kwargs['center'],self.env) is not False:self.error(node,'居中窗口可能引用未来数据，请使用向后窗口')
    return Info('window',None if receiver.lookback is None else receiver.lookback+value-1)
   return Info('window',None)
  if method in AGGREGATES:
   if receiver.kind!='window' and self.axis(node) not in (1,'columns'):
    self.error(node,'截面 '+method+' 必须显式 axis=1；时间序列统计请先使用向后滚动/累积窗口，不能使用全区间未来数据')
   return Info('matrix',combined_lookback)
  if method in ('shift','diff','pct_change'):
   lag=node.args[0] if node.args else kwargs.get('periods');value=_literal(lag,self.env) if lag else 1
   if type(value) is not int or not 0<=value<=MAX_LOOKBACK:self.error(node,'只支持0至504的固定非负滞后，禁止向未来取值')
   return Info('matrix',None if receiver.lookback is None else receiver.lookback+value)
  if method=='fillna' and 'method' in kwargs and _literal(kwargs['method'],self.env) not in ('ffill','pad',None):self.error(node,'禁止使用未来值向前回填，请明确缺失值处理')
  if method in ('to_numpy','any','all'):self.error(node,'因子表达式不支持全矩阵聚合或丢失日期对齐；有效值检测由执行器完成')
  if method=='pow':
   power=_literal(node.args[0],self.env) if node.args else _literal(kwargs.get('other'),self.env)
   if type(power) not in (int,float) or abs(power)>16:self.error(node,'幂运算需要有界固定指数')
  return Info(receiver.kind if receiver.kind!='window' else 'matrix',combined_lookback)
 def block(self,body):
  for node in body:
   if isinstance(node,ast.Assign):
    info=self.expression(node.value)
    for target in node.targets:self.env[target.id]=info
   elif isinstance(node,ast.Return):self.returns.append(self.expression(node.value))
   elif isinstance(node,ast.If):self.expression(node.test);self.block(node.body);self.block(node.orelse)
   elif isinstance(node,ast.Raise):
    if node.exc:self.expression(node.exc)
   elif isinstance(node,ast.Expr):self.expression(node.value)
   else:self.error(node,'当前契约只支持明确的面板表达式、局部赋值和返回')

@lru_cache(maxsize=128)
def inspect_source(source:str,entry:str):
 try:re_validate_source(source,entry)
 except (ValueError,SyntaxError) as exc:raise ValueError('实现与研发/查重的统一源码契约不兼容：'+str(exc)+'。请保留方法名并使用唯一的一参 self 入口、固定向后滞后与支持字段。') from None
 tree=ast.parse(source);analyzer=Analyzer(tree.body[0]);analyzer.block(tree.body[0].body)
 if not analyzer.returns or any(x.kind!='matrix' for x in analyzer.returns):raise ValueError('因子必须返回按日期×股票对齐的面板')
 if _maxlook(analyzer.returns) is not None and _maxlook(analyzer.returns)>MAX_LOOKBACK:raise ValueError('组合回看超过504个观测，超出当前有界实现契约')
 wrapped=validated_factor_code(source,entry)
 try:re_validate_source(wrapped,entry)
 except (ValueError,SyntaxError) as exc:raise ValueError('执行有效值包装与当前查重入口不兼容：'+str(exc)) from None
 return {'version':VERSION,'re_policy_sha256':RE_POLICY_SHA256,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'wrapped_source_sha256':hashlib.sha256(wrapped.encode()).hexdigest(),'lookback_sessions':_maxlook(analyzer.returns),'fields':sorted({n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) and n.value.id=='self'}),'static_causal_check':'passed','limitations':'静态检查不证明任意Python无前视；真实数据可得性和执行资源仍需独立核验'}

def validated_quant_code(source:str,entry:str):inspect_source(source,entry);return validated_factor_code(source,entry)

def generation_instructions():
 return '统一源码契约 '+VERSION+'：保留指定因子名，仅一个 def name(self)，禁止默认参数/装饰器/辅助函数；函数内可声明固定参数，shift/diff/pct_change 的滞后必须写非负整数字面量。字段仅 '+','.join(sorted(FIELDS))+'。截面rank/mean/std等显式axis=1或columns，时序统计必须先rolling/ewm/expanding向后窗口；禁止全区间rank/聚合回填、负shift、bfill或居中窗口。返回日期×股票DataFrame。不能实现则说明原因，不能改假设、方向、IC口径或门槛。'
