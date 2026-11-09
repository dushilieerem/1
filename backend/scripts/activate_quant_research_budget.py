"""Explicit operator application of the PM-recorded user authorization. No model call."""
import argparse,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'backend'))
parser=argparse.ArgumentParser();parser.add_argument('--org',type=int,required=True);parser.add_argument('--actor-user',type=int,required=True);parser.add_argument('--authorization',required=True);parser.add_argument('--history-audit',required=True);parser.add_argument('--apply-authorized',action='store_true');args=parser.parse_args()
if not args.apply_authorized or args.org!=261:raise SystemExit('Only explicit current-institution authorization activation is supported')
authorization=(root/args.authorization).resolve();audit=(root/args.history_audit).resolve()
if root not in authorization.parents or root not in audit.parents:raise SystemExit('Evidence must stay within this checkout')
from services.core.db import get_conn
from services.core import migrations
from services.quant_factor import model_budget
with get_conn() as c:
 member=c.execute("SELECT id FROM inst_members WHERE org_id=%s AND user_id=%s AND status='active'",(args.org,args.actor_user)).fetchone()
 if not member:raise SystemExit('Activation actor is not an active member of the authorized institution')
state=migrations.status();pending=state.get('pending') or []
if any(row['version']!='0038_quant_ai_budget' or row.get('changed') for row in pending):raise SystemExit('Unexpected pending/changed migration; refusing broad application')
applied=migrations.apply_migrations() if pending else {'ok':True,'applied':[]}
legacy=model_budget.record_legacy_audit(args.org,args.actor_user,audit)
first=model_budget.install_authorization(args.org,args.actor_user,authorization)
again=model_budget.install_authorization(args.org,args.actor_user,authorization)
assert first['id']==again['id']
print(json.dumps({'migration':{'ok':applied['ok'],'applied':applied.get('applied',[])},'authorization':{'id':first['id'],'org_id':first['org_id'],'authorized_by':first['authorized_by'],'limit_tokens':first['limit_tokens'],'idempotent_replay_same_id':True},'legacy':legacy,'status':model_budget.status(args.actor_user,args.org)},ensure_ascii=False,indent=2))
