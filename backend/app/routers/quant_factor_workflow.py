from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,ConfigDict,Field
from app.deps import require_quant_user
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
def candidates(project_id:str,ctx=Depends(require_quant_user)):
    return {'candidates':invoke(store.list_candidates,*identity(ctx),project_id)}
@router.post('/projects/{project_id}/candidates',status_code=202)
def create(project_id:str,ctx=Depends(require_quant_user)):
    return invoke(service.create,*identity(ctx),project_id)
@router.get('/candidates/{cid}')
def get(cid:str,ctx=Depends(require_quant_user)):return invoke(service.current,*identity(ctx),cid)
@router.post('/candidates/{cid}/validate',status_code=202)
def validate(cid:str,ctx=Depends(require_quant_user)):return invoke(service.validate,*identity(ctx),cid)
@router.post('/candidates/{cid}/cancel')
def cancel(cid:str,ctx=Depends(require_quant_user)):return invoke(service.cancel,*identity(ctx),cid)
@router.post('/candidates/{cid}/archive')
def archive(cid:str,body:ArchiveBody,ctx=Depends(require_quant_user)):return invoke(service.archive,*identity(ctx),cid,body.note)
@router.post('/candidates/{cid}/submit')
def submit(cid:str,ctx=Depends(require_quant_user)):
    invoke(service.current,*identity(ctx),cid)
    raise HTTPException(409,'尚无跨研究接口的封存权限及独立审批角色，不开放正式准入。可保存研究证据和留档。')
class RegisterBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    library_id:int=Field(gt=0)
@router.post('/candidates/{cid}/register')
def register(cid:str,body:RegisterBody,ctx=Depends(require_quant_user)):
    try:return invoke(service.register_asset,*identity(ctx),cid,body.library_id)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
class DraftBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    hypothesis:str=Field(default='',max_length=3000)
    target:str=Field(default='',max_length=500)
    acceptance:str=Field(default='',max_length=2000)
    candidate_id:str|None=Field(default=None,max_length=100)
@router.post('/projects/{project_id}/assistant')
def assistant(project_id:str,body:DraftBody,request:Request,ctx=Depends(require_quant_user)):
    from services.core.rate_limit import enforce_rate_limit
    enforce_rate_limit(request,scope='quant.factor.assistant',limit=6,window_sec=60)
    from ai.errors import AiError
    from pydantic import ValidationError
    from services.quant_factor.assistant import suggest
    try:return invoke(suggest,*identity(ctx),project_id,body.model_dump(exclude={'candidate_id'}),body.candidate_id)
    except PermissionError as exc:raise HTTPException(429,str(exc)) from exc
    except (AiError,ValidationError,ValueError) as exc:raise HTTPException(502,'研究助手暂未返回有效建议，请稍后重试；原内容未更改。') from exc
