from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,ConfigDict,Field
from app.deps import require_quant_researcher, require_quant_reviewer
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

@router.get('/reviews')
def review_queue(ctx=Depends(require_quant_reviewer)):
    from services.quant_factor.review import queue
    return {'candidates':invoke(queue,*identity(ctx))}

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
