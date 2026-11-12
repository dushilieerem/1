"""Member-scoped operational facts for the institutional workspace."""
from datetime import datetime,timezone
from services.core.db import get_conn

def overview(uid,org):
    with get_conn() as c:
        projects=c.execute("SELECT id,name,updated_at,config FROM detect_projects WHERE user_id=%s ORDER BY updated_at DESC LIMIT 100",(uid,)).fetchall()
        factor_count=c.execute('SELECT COUNT(*) AS n FROM detect_projects WHERE user_id=%s',(uid,)).fetchone()['n']
        strategy_count=c.execute('SELECT COUNT(*) AS n FROM strategy_projects WHERE user_id=%s',(uid,)).fetchone()['n']
        counts=c.execute("SELECT COUNT(*) AS candidates,COUNT(*) FILTER(WHERE status LIKE '%%_running') AS running,COUNT(*) FILTER(WHERE status LIKE '%%_error') AS errors,COUNT(*) FILTER(WHERE archive->'review'->>'status'='requested') AS pending_review,(SELECT COUNT(*) FROM quant_factor_sealed_validations WHERE user_id=%s AND org_id=%s) AS sealed_used FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s",(uid,org,uid,org)).fetchone()
        rows=c.execute("SELECT id,project_id,snapshot->>'name' AS name,snapshot_hash,status,archive,events,updated_at,evidence->'development'->'result'->'meta' AS data_meta FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s ORDER BY updated_at DESC LIMIT 30",(uid,org)).fetchall()
    tasks=[]
    for p in projects:
        cfg=p['config'] or {};stage='F2'
        if cfg.get('researchPlan',{}).get('revision'):stage='F3'
        if cfg.get('factorCodes'):stage='F4'
        latest=next((r for r in rows if r['project_id']==p['id']),None)
        if latest and (latest['status']=='development_passed' or latest['status'].startswith('validation_')):stage='F5'
        if latest and latest['archive']:stage='F6'
        tasks.append({'id':p['id'],'name':p['name'],'stage':stage,'status':latest['status'] if latest else 'draft','updated_at':p['updated_at']})
    events=[]
    for r in rows:
        for e in (r['events'] or [])[-10:]:events.append({**e,'candidate_id':r['id'],'project_id':r['project_id'],'name':r['name']})
    events.sort(key=lambda e:e.get('at',''),reverse=True)
    return {'scope':'member_private','updated_at':datetime.now(timezone.utc).isoformat(),'counts':{**dict(counts),'factor_projects':factor_count,'strategy_projects':strategy_count},'tasks':tasks,'candidates':[{k:v for k,v in dict(r).items() if k!='events'} for r in rows],'events':events[:30],'limited':{'factor_projects':100,'candidates':30,'events':30}}
