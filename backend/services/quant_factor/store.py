from __future__ import annotations
import json
from services.core.db import get_conn

def encode(value): return json.dumps(value,ensure_ascii=False,allow_nan=False)

def read(uid,org,candidate_id):
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s',(candidate_id,uid,org)).fetchone()
    if not row: raise KeyError(candidate_id)
    return dict(row)

def list_candidates(uid,org,project):
    with get_conn() as c:
        rows=c.execute('SELECT id,project_id,snapshot_hash,status,created_at,updated_at,evidence,archive FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND project_id=%s ORDER BY created_at DESC LIMIT 100',(uid,org,project)).fetchall()
    # Results stay on detail endpoint; list contains only gate summaries.
    return [{**dict(r),'evidence':{k:{'gate':v.get('gate'),'run_id':v.get('run_id')} for k,v in (r['evidence'] or {}).items()}} for r in rows]

def update(uid,org,cid,status,event,evidence=None):
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(cid,uid,org)).fetchone()
        if not row: raise KeyError(cid)
        if row['status']=='cancelled': return False
        ev=dict(row['evidence'] or {});ev.update(evidence or {})
        c.execute('UPDATE quant_factor_candidates SET status=%s,evidence=%s::jsonb,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s',(status,encode(ev),encode([event]),cid))

