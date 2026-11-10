"""Explicit product authorization activation. No model call; no shared quota changes."""
import argparse,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'backend'))
p=argparse.ArgumentParser();p.add_argument('--org',type=int,required=True);p.add_argument('--actor-user',type=int,required=True);p.add_argument('--authorization',required=True);p.add_argument('--apply-authorized',action='store_true');args=p.parse_args()
if not args.apply_authorized or args.org!=261:raise SystemExit('Explicit current-institution activation required')
path=(root/args.authorization).resolve()
if root not in path.parents:raise SystemExit('Authorization evidence must stay within checkout')
from services.quant_factor import token_policy,model_budget
# Migration is an independent reviewed operation, never broad auto-apply here.
first=token_policy.install(args.org,args.actor_user,path);again=token_policy.install(args.org,args.actor_user,path)
assert first['id']==again['id']
print(json.dumps({'id':first['id'],'mode':first['mode'],'org_id':first['org_id'],'idempotent':True,'status':model_budget.status(args.actor_user,args.org)},ensure_ascii=False,indent=2))
