"""Conservative identity of validated panel source; never a novelty certificate."""
import ast
import copy
import hashlib
from .research_contract import fingerprint

def canonical(source, entry=None):
 from .source_contract import inspect_source
 tree=ast.parse(source)
 if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef):raise ValueError('single factor method required')
 inspect_source(source,entry or tree.body[0].name) # Validate before considering equivalence.
 tree=copy.deepcopy(tree);fn=tree.body[0]
 if fn.body and isinstance(fn.body[0],ast.Expr) and isinstance(fn.body[0].value,ast.Constant) and isinstance(fn.body[0].value.value,str):fn.body.pop(0)
 body=[n for stmt in fn.body for n in ast.walk(stmt)]
 # Changing entry name is safe only when it is never referenced by the body.
 if not any(isinstance(n,ast.Name) and n.id==fn.name or isinstance(n,ast.Attribute) and n.attr==fn.name for n in body):fn.name='_factor'
 scopes=(ast.Lambda,ast.ListComp,ast.SetComp,ast.DictComp,ast.GeneratorExp,ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Global,ast.Nonlocal)
 if not any(isinstance(n,scopes) for n in body):
  args={n.arg for n in ast.walk(fn.args) if isinstance(n,ast.arg)}
  locals_in_order=list(dict.fromkeys(n.id for n in body if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store) and n.id not in args))
  # Generated identifiers must be disjoint from EVERY original identifier,
  # including free globals and parameters, not just from the locals being renamed.
  reserved={n.id for n in body if isinstance(n,ast.Name)}|args
  prefix='_canonical_local_'
  while any((prefix+str(i)) in reserved for i in range(len(locals_in_order))):prefix='_'+prefix
  mapping={name:prefix+str(i) for i,name in enumerate(locals_in_order)}
  for n in body:
   if isinstance(n,ast.Name) and n.id in mapping:n.id=mapping[n.id]
 return ast.dump(tree,include_attributes=False)

def identity(source,entry=None):return hashlib.sha256(canonical(source,entry).encode()).hexdigest()

def execution_key(snapshot):
 """Code equivalence is reusable only under all the same frozen conditions."""
 request=copy.deepcopy(snapshot['request']);code=request.pop('factor_code',None);name=request.pop('factor_name',None)
 if not code:raise ValueError('Cannot prove equivalence of an unresolved library definition')
 plan=snapshot['plan']
 conditions={'request':request,'rules':snapshot['rules'],'contract':plan.get('researchContract'),
  'development':[plan.get('developmentStart'),plan.get('developmentEnd')],
  'validation':[plan.get('validationStart'),plan.get('validationEnd')],
  'data_release':plan.get('dataReleaseId'),'method_version':(plan.get('researchContract') or {}).get('method_identity'),
  'source_research_asset':snapshot.get('sourceResearchAsset')}
 # Missing frozen contract is intentionally ineligible for new-method reuse.
 if not conditions['contract']:raise ValueError('Legacy execution has no frozen research contract')
 return fingerprint({'source_ast':identity(code,name),'conditions':conditions})
