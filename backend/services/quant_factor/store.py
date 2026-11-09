from __future__ import annotations
import json
from services.core.db import get_conn
from services.core.tenant import Tenant
from . import repo

def encode(value): return json.dumps(value,ensure_ascii=False,allow_nan=False)

def read(uid,org,candidate_id):
    return repo.candidate(Tenant.from_pair(uid,org),candidate_id)

def summarize_evidence(evidence,include_numbers=False):
    """Evidence also contains branch IDs/method provenance, not only phase objects."""
    out={}
    for phase in ('development','validation'):
        block=(evidence or {}).get(phase)
        if not isinstance(block,dict):continue
        summary={'gate':block.get('gate'),'run_id':block.get('run_id')}
        if include_numbers:
            result=block.get('result') or {}
            summary.update(metrics=result.get('metrics'),meta=result.get('meta'))
        out[phase]=summary
    return out


def list_candidates(uid,org,project):
    rows=repo.candidates(Tenant.from_pair(uid,org),project)
    # Stable display identity is derived from the actual tenant-scoped ledger.
    from .presentation import context,candidate_identity
    facts=context(uid,org,project)
    return [{**r,'presentation':candidate_identity(r,facts),'evidence':summarize_evidence(r.get('evidence'))} for r in rows]

def update(uid,org,cid,status,event,evidence=None):
    t=Tenant.from_pair(uid,org)
    with get_conn() as c:
        row=c.execute('SELECT * FROM quant_factor_candidates WHERE id=%s AND user_id=%s AND org_id=%s FOR UPDATE',(cid,t.user_id,t.org_id)).fetchone()
        if not row: raise KeyError(cid)
        if row['status']=='cancelled': return False
        ev=dict(row['evidence'] or {});ev.update(evidence or {})
        c.execute('UPDATE quant_factor_candidates SET status=%s,evidence=%s::jsonb,events=events||%s::jsonb,updated_at=NOW() WHERE id=%s',(status,encode(ev),encode([event]),cid))
