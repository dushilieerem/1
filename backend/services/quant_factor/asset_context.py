"""Permission-scoped factor-library context; metadata is not numeric novelty proof."""
import ast
import hashlib
import json
from .policy import WorkflowError,digest

def code_identity(source):
    """Ignore function/local names and docstrings; never execute source code."""
    try:
        tree=ast.parse(source)
        f=tree.body[0]
        if len(tree.body)!=1 or not isinstance(f,ast.FunctionDef):return None
        names={}
        for a in f.args.posonlyargs+f.args.args+f.args.kwonlyargs:
            if a.arg!='self':names.setdefault(a.arg,'v'+str(len(names)))
        for n in ast.walk(f):
            if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store):names.setdefault(n.id,'v'+str(len(names)))
        class Canonical(ast.NodeTransformer):
            def visit_FunctionDef(self,node):
                node.name='_factor'
                if node.body and isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant) and isinstance(node.body[0].value.value,str):node.body=node.body[1:]
                return self.generic_visit(node)
            def visit_Name(self,node):
                if node.id in names:node.id=names[node.id]
                return node
            def visit_arg(self,node):
                node.arg=names.get(node.arg,node.arg)
                return node
        return hashlib.sha256(ast.dump(Canonical().visit(tree),include_attributes=False).encode()).hexdigest()
    except (SyntaxError,ValueError,TypeError,IndexError):return None

def catalogue(uid, org=None):
    from services.factor.re_factor_catalog import fetch_re_catalog
    from services.factor.user_library_store import list_all_user_library_factors
    raw=fetch_re_catalog(include_all=True)
    if not raw.get('ok') or raw.get('errors') or not raw.get('factors'):
        raise WorkflowError('因子库目录读取不完整，暂停新因子选题；请恢复目录后重试。')
    builtins=[{'library_name':f['library'],'factor_name':f['name'],'description':str(f.get('display_name') or '')+'：'+str(f.get('description') or ''),'category':f.get('category_name') or f.get('category_label') or ''} for f in raw['factors']]
    owned=[{'factor_name':f['name'],'factor_code':f['body'],'source_id':'user:'+str(f['id']),'library_name':f.get('libraryName',''),'description':f.get('description','')} for f in list_all_user_library_factors(uid) if f.get('formulaReady') and f.get('body')]
    pending=[]
    if org is not None:
        from services.core.db import get_conn
        with get_conn() as c:
            rows=c.execute(
                "SELECT id,snapshot->'request'->>'factor_name' AS factor_name,snapshot->'request'->>'factor_code' AS factor_code,snapshot->'request'->>'library_name' AS library_name FROM quant_factor_candidates WHERE org_id=%s AND archive->'review'->>'status'='requested' ORDER BY updated_at DESC",(org,)).fetchall()
        pending=[{'factor_name':r['factor_name'],'factor_code':r['factor_code'],'source_id':'pending:'+r['id'],'library_name':'本机构待审候选','description':'同机构待审候选 '+(r['factor_name'] or '')} for r in rows if r.get('factor_code')]
    identities=[{'id':f['library_name']+':'+f['factor_name'],'metadata_hash':digest(f)} for f in builtins]+[{'id':f['source_id'],'hash':hashlib.sha256(f['factor_code'].encode()).hexdigest()} for f in owned+pending]
    return {'scope':'平台内置目录、当前账号已有可计算定义的自建因子、本机构待审候选；不含无代码草稿和其他成员私有库','builtins':builtins,'owned':owned+pending,'hash':digest(identities),'catalogue_fetched_at':raw.get('fetched_at'),'count':len(identities)}

def planner_context(refs):
    # Full visible metadata within a bounded context. Never silently truncate then claim full coverage.
    records=[{'id':f['library_name']+':'+f['factor_name'],'definition':f['description'][:140],'definition_truncated':len(f['description'])>140} for f in refs['builtins']]
    records += [{'id':f['source_id'],'name':f['factor_name'],'definition':f['description'][:160],'code':f['factor_code'][:1500],'definition_truncated':len(f['description'])>160,'code_truncated':len(f['factor_code'])>1500} for f in refs['owned']]
    if len(json.dumps(records,ensure_ascii=False))>100000:
        raise WorkflowError('因子库选题上下文超过当前上限，需要分批检索；未把截断目录冒充完整检索。')
    return {'scope':refs['scope'],'count':refs['count'],'catalogue_fetched_at':refs.get('catalogue_fetched_at'),'reference_hash':refs['hash'],'references':records,'limitation':'覆盖全部目录条目，每条提供有限长度摘要并标明截断；不代表已逐行阅读全部源码。目录检索不等于因子值相关性或增量检验。'}

def duplicate_matches(code,refs):
    sha=code_identity(code)
    if not sha:return []
    return [{'name':f['factor_name'],'source_id':f['source_id'],'library':f['library_name']} for f in refs['owned'] if code_identity(f['factor_code'])==sha]
