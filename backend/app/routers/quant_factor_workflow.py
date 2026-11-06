from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,ConfigDict,Field
from app.deps import require_quant_manager, require_quant_researcher, require_quant_reviewer, require_quant_user
from app.routers.inst_quant import _quant_uid
from services.quant_factor import service,store
from services.quant_factor.policy import WorkflowError
router=APIRouter(prefix='/api/inst/quant/factor-workflow',tags=['quant-factor-workflow'])
class ArchiveBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    note:str=Field(min_length=1,max_length=3000)
def identity(ctx): return _quant_uid(ctx),int(ctx['org']['id'])
def invoke(fn,*args):
    try:return fn(*args)
    except KeyError:raise HTTPException(404,'记录不存在或无权访问') from None
    except WorkflowError as exc:raise HTTPException(409,str(exc)) from exc
@router.get('/projects/{project_id}/candidates')
def candidates(project_id:str,ctx=Depends(require_quant_researcher)):
    return {'candidates':invoke(store.list_candidates,*identity(ctx),project_id)}
@router.post('/projects/{project_id}/candidates',status_code=202)
def create(project_id:str,ctx=Depends(require_quant_researcher)):
    return invoke(service.create,*identity(ctx),project_id)
@router.get('/candidates/{cid}')
def get(cid:str,ctx=Depends(require_quant_researcher)):return invoke(service.current,*identity(ctx),cid)
@router.post('/candidates/{cid}/validate',status_code=202)
def validate(cid:str,ctx=Depends(require_quant_researcher)):return invoke(service.validate,*identity(ctx),cid)
@router.post('/candidates/{cid}/novelty/retry',status_code=202)
def retry_novelty(cid:str,ctx=Depends(require_quant_researcher)):
    return invoke(service.retry_novelty,*identity(ctx),cid)
@router.post('/candidates/{cid}/cancel')
def cancel(cid:str,ctx=Depends(require_quant_researcher)):return invoke(service.cancel,*identity(ctx),cid)
@router.post('/candidates/{cid}/archive')
def archive(cid:str,body:ArchiveBody,ctx=Depends(require_quant_researcher)):return invoke(service.archive,*identity(ctx),cid,body.note)
@router.post('/candidates/{cid}/submit')
def submit(cid:str,ctx=Depends(require_quant_researcher)):
    invoke(service.current,*identity(ctx),cid)
    raise HTTPException(409,'尚无跨研究接口的封存权限与正式准入服务，不开放正式准入。可保存研究证据和留档。')
class RegisterBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    library_id:int=Field(gt=0)
@router.post('/candidates/{cid}/register')
def register(cid:str,body:RegisterBody,ctx=Depends(require_quant_researcher)):
    try:return invoke(service.register_asset,*identity(ctx),cid,body.library_id)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
class DraftBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    hypothesis:str=Field(default='',max_length=3000)
    target:str=Field(default='',max_length=500)
    acceptance:str=Field(default='',max_length=2000)
    candidate_id:str|None=Field(default=None,max_length=100)
@router.post('/projects/{project_id}/assistant')
def assistant(project_id:str,body:DraftBody,request:Request,ctx=Depends(require_quant_researcher)):
    from services.core.rate_limit import enforce_rate_limit
    enforce_rate_limit(request,scope='quant.factor.assistant',limit=6,window_sec=60)
    from ai.errors import AiError
    from pydantic import ValidationError
    from services.quant_factor.assistant import suggest
    try:return invoke(suggest,*identity(ctx),project_id,body.model_dump(exclude={'candidate_id'}),body.candidate_id)
    except PermissionError as exc:raise HTTPException(429,str(exc)) from exc
    except (AiError,ValidationError,ValueError) as exc:raise HTTPException(502,'研究助手暂未返回有效建议，请稍后重试；原内容未更改。') from exc

class ReviewBody(ArchiveBody):
    decision: str = Field(pattern='^(research_supported|needs_revision|rejected)$')

@router.post('/candidates/{cid}/review-request')
def review_request(cid:str,body:ArchiveBody,ctx=Depends(require_quant_researcher)):
    from services.quant_factor.review import request_review
    return invoke(request_review,*identity(ctx),cid,body.note)

@router.get('/pending-review-count')
def pending_review_count(ctx=Depends(require_quant_user)):
    from services.quant_factor import review
    uid,org=identity(ctx)
    return {'count':invoke(review.pending_count,org,uid,bool(ctx.get('can_review')))}

@router.get('/reviews')
def review_queue(ctx=Depends(require_quant_reviewer)):
    from services.quant_factor.review import queue
    return {'candidates':invoke(queue,*identity(ctx))}

@router.post('/reviews/{cid}/claim')
def review_claim(cid:str,ctx=Depends(require_quant_reviewer)):
    from services.quant_factor.review import claim
    return invoke(claim,*identity(ctx),cid)

@router.get('/reviews/{cid}')
def review_detail(cid:str,ctx=Depends(require_quant_reviewer)):
    from services.quant_factor.review import detail
    return invoke(detail,*identity(ctx),cid)

@router.post('/reviews/{cid}')
def review_record(cid:str,body:ReviewBody,ctx=Depends(require_quant_reviewer)):
    from services.quant_factor.review import record
    return invoke(record,*identity(ctx),cid,body.decision,body.note)

@router.get('/overview')
def workspace_overview(ctx=Depends(require_quant_researcher)):
    from services.quant_factor.dashboard import overview
    return invoke(overview,*identity(ctx))

class AgentDraftBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    stage:str=Field(pattern='^F[123]$')
    project_id:str|None=Field(default=None,max_length=100)
    draft:dict[str,str]=Field(default_factory=dict,max_length=12)
    request_key:str|None=Field(default=None,max_length=100)

@router.get('/agent-jobs/latest')
def agent_latest(stage:str,project_id:str|None=None,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import agent_jobs
    return {'job':invoke(agent_jobs.latest,*identity(ctx),stage,project_id)}

@router.post('/agent-jobs',status_code=202)
def agent_start(body:AgentDraftBody,request:Request,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import agent_jobs
    from services.core.rate_limit import enforce_rate_limit
    if sum(len(v) for v in body.draft.values())>20000:raise HTTPException(422,'研究输入过长')
    enforce_rate_limit(request,scope='quant.factor.agent',limit=12,window_sec=60)
    try:return invoke(agent_jobs.create,*identity(ctx),body.stage,body.project_id,body.draft,body.request_key)
    except PermissionError as exc:raise HTTPException(429,str(exc)) from exc

@router.get('/agent-jobs/{jid}')
def agent_status(jid:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import agent_jobs
    return invoke(agent_jobs.read,*identity(ctx),jid)

@router.post('/agent-jobs/{jid}/cancel')
def agent_cancel(jid:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import agent_jobs
    return invoke(agent_jobs.cancel,*identity(ctx),jid)

class IterationBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    max_rounds:int=Field(default=3,ge=1,le=20,strict=True)

@router.get('/projects/{project_id}/iterations/latest')
def iteration_latest(project_id:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import iterations
    return {'iteration':invoke(iterations.latest,*identity(ctx),project_id)}

@router.post('/projects/{project_id}/iterations',status_code=202)
def iteration_start(project_id:str,body:IterationBody,request:Request,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import iterations
    from services.core.rate_limit import enforce_rate_limit
    enforce_rate_limit(request,scope='quant.factor.iteration',limit=6,window_sec=60)
    return invoke(iterations.start,*identity(ctx),project_id,body.max_rounds)

@router.get('/iterations/{jid}')
def iteration_get(jid:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import iterations
    return invoke(iterations.read,*identity(ctx),jid)

@router.post('/iterations/{jid}/pause')
def iteration_pause(jid:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import iterations
    return invoke(iterations.pause,*identity(ctx),jid)

class TopicBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    view_id:str=Field(min_length=1,max_length=200)
    release_id:str=Field(default='',max_length=200)
    release_ids:dict=Field(default_factory=dict)
    view_manifest_sha256:str=Field(default='',max_length=64)
    contract_revision:str=Field(default='',max_length=200)
    as_of:str|None=Field(default=None,max_length=10)
    development_start:str=Field(min_length=10,max_length=10)
    development_end:str=Field(min_length=10,max_length=10)
    validation_start:str=Field(min_length=10,max_length=10)
    validation_end:str=Field(min_length=10,max_length=10)
    primary_holding_period:int=Field(ge=1,le=20,strict=True)
    policy_version:str=Field(min_length=1,max_length=100)
    max_trials:int=Field(ge=1,le=1000,strict=True)
    max_sealed:int=Field(default=3,ge=1,le=3,strict=True)

class BranchBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source:str=Field(pattern='^(agent|manual)$')
    parent_id:str|None=Field(default=None,max_length=100)
    hypothesis_version:int=Field(default=1,ge=1,strict=True)
    implementation_version:int=Field(default=1,ge=1,strict=True)

class TrialBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    branch_id:str=Field(min_length=1,max_length=100)
    implementation_hash:str=Field(min_length=1,max_length=200)
    kind:str=Field(default='research',pattern='^(research|manual|agent|iteration)$')
    parameters:dict=Field(default_factory=dict)
    result_summary:dict=Field(default_factory=dict)
    report_id:str|None=Field(default=None,max_length=200)
    executor:str=Field(pattern='^(human|agent|service)$')
    outcome:str=Field(pattern='^(passed|failed|error|timeout|cancelled)$')
    holding_period:int|None=Field(default=None,ge=1,le=20,strict=True)

def invoke_ledger(fn,*args):
    try:return invoke(fn,*args)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc

@router.post('/projects/{project_id}/topics')
def topic_create(project_id:str,body:TopicBody,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import ledger
    return invoke_ledger(ledger.create_topic,*identity(ctx),project_id,body.model_dump())

@router.get('/topics')
def topic_list_all(ctx=Depends(require_quant_researcher)):
    from services.quant_factor import ledger
    return {'topics':invoke(ledger.list_org_topics,*identity(ctx))}

@router.get('/projects/{project_id}/topics')
def topic_list(project_id:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import ledger
    return {'topics':invoke(ledger.list_topics,*identity(ctx),project_id)}

@router.get('/topics/{tid}/ledger')
def ledger_get(tid:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import ledger
    return invoke(ledger.ledger_view,*identity(ctx),tid)

@router.get('/topics/{tid}/threshold')
def ledger_threshold(tid:str,k:int|None=None,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import ledger
    return invoke_ledger(ledger.threshold_view,*identity(ctx),tid,k)

@router.get('/topics/{tid}/branches')
def branch_list(tid:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import ledger
    return {'branches':invoke(ledger.list_branches,*identity(ctx),tid)}

@router.post('/topics/{tid}/branches')
def branch_create(tid:str,body:BranchBody,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import ledger
    return invoke_ledger(ledger.create_branch,*identity(ctx),tid,body.model_dump())

@router.post('/topics/{tid}/branches/{bid}/takeover')
def branch_takeover(tid:str,bid:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import ledger
    return invoke_ledger(ledger.takeover_branch,*identity(ctx),tid,bid)

@router.post('/topics/{tid}/pause')
def topic_pause(tid:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import ledger
    return invoke_ledger(ledger.set_topic_status,*identity(ctx),tid,'paused')

@router.post('/topics/{tid}/resume')
def topic_resume(tid:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import ledger
    return invoke_ledger(ledger.set_topic_status,*identity(ctx),tid,'active')

@router.post('/topics/{tid}/branches/{bid}/activate')
def branch_activate(tid:str,bid:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import ledger
    return invoke_ledger(ledger.activate_branch,*identity(ctx),tid,bid)

@router.post('/topics/{tid}/handback')
def branch_handback(tid:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import ledger
    return invoke_ledger(ledger.handback_branch,*identity(ctx),tid)

@router.post('/topics/{tid}/trials')
def trial_append(tid:str,body:TrialBody,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import ledger
    return invoke_ledger(ledger.append_trial,*identity(ctx),tid,body.model_dump())


@router.post('/imports/svquant-existing')
def import_existing(ctx=Depends(require_quant_manager)):
    from services.quant_factor import imports
    return invoke(imports.sync_existing,*identity(ctx))

@router.get('/imports/svquant-existing')
def import_summary(ctx=Depends(require_quant_researcher)):
    from services.quant_factor import imports
    return invoke(imports.summary,*identity(ctx))

class MetricsBatchBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    limit:int=Field(default=5,ge=1,le=20,strict=True)

@router.post('/imports/metrics-batch',status_code=202)
def import_metrics_start(body:MetricsBatchBody,ctx=Depends(require_quant_manager)):
    from services.quant_factor import import_metrics
    return invoke_ledger(import_metrics.start_batch,*identity(ctx),body.limit)

@router.get('/imports/metrics-batch/{batch_id}')
def import_metrics_status(batch_id:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import import_metrics
    return invoke(import_metrics.batch_status,*identity(ctx)[1:],batch_id)

@router.post('/imports/{factor_id}/metrics-retry')
def import_metrics_retry(factor_id:str,ctx=Depends(require_quant_manager)):
    from services.quant_factor import import_metrics
    return invoke(import_metrics.retry_one,*identity(ctx),factor_id)

@router.get('/imports/svquant-existing/reference')
def import_reference(ctx=Depends(require_quant_researcher)):
    from services.quant_factor import imports
    return invoke(imports.reference_inventory,*identity(ctx))



@router.post('/candidates/{cid}/sealed-validation',status_code=202)
def sealed_request(cid:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import sealed
    return invoke(sealed.request,*identity(ctx),cid)

@router.get('/candidates/{cid}/sealed-validation')
def sealed_detail(cid:str,ctx=Depends(require_quant_user)):
    from services.quant_factor import sealed
    uid,org=identity(ctx)
    full=bool(ctx.get('can_review') or ctx.get('can_manage'))
    return invoke(sealed.detail,uid,org,cid,full)


class F0Body(BaseModel):
    model_config=ConfigDict(extra='forbid')
    idempotency_key:str=Field(min_length=1,max_length=100)

@router.post('/topics/{tid}/branches/{bid}/f0',status_code=202)
def f0_start(tid:str,bid:str,body:F0Body,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import f0
    return invoke_ledger(f0.start,*identity(ctx),tid,bid,body.idempotency_key)

@router.get('/topics/{tid}/f0-runs')
def f0_latest(tid:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import f0
    return invoke(f0.latest,*identity(ctx),tid)

@router.post('/f0-runs/{rid}/resume',status_code=202)
def f0_resume(rid:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import f0
    return invoke_ledger(f0.resume,*identity(ctx),rid)

@router.get('/f0-runs/{rid}')
def f0_read(rid:str,ctx=Depends(require_quant_researcher)):
    from services.quant_factor import f0
    return invoke(f0.read,*identity(ctx),rid)


@router.post('/reviews/{cid}/independent-opinion')
def independent_opinion(cid:str,ctx=Depends(require_quant_reviewer)):
    from services.quant_factor import f5
    return invoke(f5.opinion,*identity(ctx),cid)
