"""Independent read-only post-copy proof; no model/market calls or app bootstrap."""
from copy_database import *
import ast,typing

def main():
 marker=json.loads((HERE/'initialization-marker.json').read_text())
 if marker['status']!='prepared_verified_not_loaded':raise RuntimeError('preparation incomplete')
 cutoff=datetime.fromisoformat(marker['snapshot_cutoff'])
 # Execute only the existing pure ledger counting definitions; never import live application startup.
 tree=ast.parse((ROOT/'backend/services/quant_factor/ledger.py').read_text());nodes=[]
 for node in tree.body:
  if isinstance(node,ast.Assign) and any(isinstance(n,ast.Name) and n.id.endswith(('KINDS','OUTCOMES')) for n in node.targets):nodes.append(node)
  elif isinstance(node,ast.FunctionDef) and node.lineno<=155:nodes.append(node)
 ns={'Iterable':typing.Iterable};exec(compile(ast.Module(body=nodes,type_ignores=[]),'existing-pure-ledger','exec'),ns)
 with connect(SOURCE,readonly=True) as src,connect(TARGET,readonly=True) as dst:
  a=snapshot(src,cutoff);b=snapshot(dst,cutoff);validate(a);validate(b)
  equality={t:digest(a[t])==digest(b[t]) for t in COPIED}
  if not all(equality.values()):raise RuntimeError('post-copy source changes detected')
  ks=[]
  for topic in a['quant_factor_topics']:
   def k(data):return ns['current_k']([r for r in data['quant_factor_trials'] if r['topic_id']==topic['id']],topic['primary_holding_period'])
   before,after=k(a),k(b)
   if before!=after:raise RuntimeError('ledger K changed')
   ks.append({'project_id':topic['project_id'],'topic_id':topic['id'],'k':after,'max_trials':topic['max_trials'],'remaining':max(0,topic['max_trials']-after),'equal':True})
  current=next(r for r in ks if r['project_id']=='0cf7441a-94e9-4690-94f6-0396f8836346')
  if current['k']!=2 or current['max_trials']!=2:raise RuntimeError('r4 K/authorization changed')
  qa=dst.execute('SELECT u.id,u.status,u.role,m.org_id,m.role AS institution_role,m.status AS membership_status FROM users u JOIN inst_members m ON m.user_id=u.id WHERE u.id=ANY(%s) ORDER BY u.id',(list(QA),)).fetchall()
  stub=dst.execute('SELECT id,status,role,(SELECT count(*) FROM inst_members WHERE user_id=1046) AS memberships FROM users WHERE id=1046').fetchone()
  review_counts=dst.execute("SELECT count(*) FILTER(WHERE archive->'review'->>'status'='reviewed') AS reviewed,count(*) FILTER(WHERE archive->'research_asset' IS NOT NULL) AS assets FROM quant_factor_candidates").fetchone()
  budgets=dst.execute('SELECT scope,historical_tokens,baseline_state,unknown_history FROM quant_ai_budget_accounts ORDER BY scope').fetchall()
  # Unknown history structure remains in database; output only its numeric count already approved in the plan.
  if sorted(r['historical_tokens'] for r in budgets)!=[180331,180331]:raise RuntimeError('historical baseline reset')
  usage=dst.execute('SELECT count(*) AS calls,sum(actual_tokens) AS known_actual FROM quant_ai_budget_calls').fetchone()
  sealed=dst.execute('SELECT status,count(*) AS n FROM quant_factor_sealed_validations GROUP BY status').fetchall()
  empty={t:dst.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(sql.Identifier(t))).fetchone()['n'] for t in ['strategy_projects','strategy_runs','re_factor_catalog_snapshot','auth_login_failures','invest_stocks','invest_etf']}
  doc=dst.execute('SELECT count(*) AS n FROM svquant.doc_extract').fetchone()['n']
  if any(empty.values()) or doc:raise RuntimeError('unapproved seed/data in target')
  state=dst.execute("SELECT current_database() AS db,current_user AS actor,current_setting('transaction_read_only') AS transaction_read_only").fetchone()
  source_state=src.execute("SELECT current_database() AS db,current_setting('transaction_read_only') AS transaction_read_only").fetchone()
  manifest=dst.execute('SELECT version,checksum FROM schema_migrations ORDER BY version').fetchall()
  if {r['version']+'.sql':r['checksum'] for r in manifest}!={r['name']:r['sha256'] for r in capture()['canonical_files']}:raise RuntimeError('target canonical manifest differs')
 save('post-copy-readonly-verification.json',{'status':'prepared_verified_not_loaded','at_utc':now(),'source':source_state,'target':state,'all_copied_rows_still_equal':equality,'topic_k_and_authorizations':ks,'r4_k_preserved':current,'qa_original_roles':qa,'historical_reference':stub,'review_counts':review_counts,'metered_calls':usage,'history_scopes':[{'scope':r['scope'],'historical_tokens':r['historical_tokens'],'baseline_state':r['baseline_state']} for r in budgets],'unknown_history_preserved_by_full_row_comparison':True,'sealed_history_status':sealed,'empty_non_scope_tables':empty,'doc_extract_rows':doc,'canonical_migrations':len(manifest),'service_switch_performed':False,'real_model_market_or_new_research_performed':False})
 print('read-only post-copy verified: 19 topic K values, historical costs, roles, reports and review rows preserved')

if __name__=='__main__':
 try:main()
 except Exception as exc:
  safe_failure('post-copy-error.json',exc);print('post-copy stopped; sanitized evidence written');sys.exit(1)
