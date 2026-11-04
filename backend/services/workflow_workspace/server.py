"""Loopback product API and actual workbench. No production identity bypass."""
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse,FileResponse,Response,RedirectResponse
from fastapi.staticfiles import StaticFiles
from .service import Workspace,rpc
from .task_agent import TaskAgent
from .tasks import ResearchTasks,Conflict

def create_app(root,web,engine_url,port,key=''):
    workspace=Workspace(root,engine_url);workspace.agent=TaskAgent(workspace,key);tasks=ResearchTasks(workspace)
    @asynccontextmanager
    async def lifespan(app):
        yield
        workspace.agent.pool.shutdown(wait=False,cancel_futures=True);workspace.pool.shutdown(wait=False,cancel_futures=True)
    app=FastAPI(lifespan=lifespan);app.state.workspace=workspace
    @app.middleware('http')
    async def local_guard(req:Request,call_next):
        host=req.headers.get('host','')
        allowed={f'localhost:{port}',f'127.0.0.1:{port}'}
        origin=req.headers.get('origin')
        if host not in allowed or (origin and origin not in {'http://'+h for h in allowed}) or req.headers.get('sec-fetch-site')=='cross-site':return JSONResponse({'error':'仅供本机同源工作台访问'},403)
        try:size=int(req.headers.get('content-length','0') or 0)
        except ValueError:return JSONResponse({'error':'请求长度无效'},400)
        if size>100000:return JSONResponse({'error':'请求过大'},413)
        response=await call_next(req);response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff';response.headers['Content-Security-Policy']="frame-ancestors 'none'";return response
    @app.get('/api/health')
    def health():return {'ok':True,'service':'svquant-workflow-workspace','mode':'local_research','engine':engine_url}
    @app.get('/api/state')
    def state():return workspace.state()
    @app.get('/api/v3/state')
    def task_state():return tasks.state()
    @app.get('/api/platform/data-view')
    def company_view():
        from .platform_data import published_view
        try:return published_view()
        except (ValueError, OSError):return JSONResponse({'error':'公司数据 view 未配置或发布契约不可用'},503)
    @app.get('/api/catalog')
    def catalog():
        try:return {'catalog':workspace.catalog(),'capabilities':workspace.capabilities()}
        except ValueError as e:return JSONResponse({'error':str(e)},503)
    @app.get('/api/runs/{identity}')
    def result(identity:str):
        try:return workspace.report(identity)
        except ValueError as e:return JSONResponse({'error':str(e)},404)
    @app.get('/api/runs/{identity}/export')
    def export(identity:str):
        import json
        try:job=workspace.report(identity)
        except ValueError as e:return JSONResponse({'error':str(e)},404)
        return Response(json.dumps(job,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="{job["id"]}.json"'})
    @app.post('/api/{action:path}')
    def act(action:str,body:dict):
        try:
            if action=='v3/tasks':return tasks.create(body)
            if action=='v3/tasks/update':return tasks.update(body.get('id'),body.get('revision'),body.get('patch'))
            if action=='v3/tasks/run':return tasks.execute(body.get('id'),body.get('revision'))
            if action=='v3/tasks/submit':return tasks.submit(body.get('id'),body.get('revision'),body.get('run_id'),body.get('note',''))
            if action=='v3/assistant/apply':
                a=workspace.store.get('agent',body.get('id'))
                if not a or a.get('intent')!='task_fill' or a['status']!='completed' or not a.get('form_patch'):raise ValueError('没有可采纳的 AI 草稿')
                return tasks.update(a['task_id'],a['task_revision'],a['form_patch'])
            if action=='factors':return workspace.save_factor(body)
            if action=='validate':return workspace.validate(body)
            if action=='preview':return rpc(engine_url,'/tools/preview_data',body)
            if action=='runs':return workspace.run(body.get('kind'),body)
            if action=='cancel':return workspace.cancel(body.get('id'))
            if action=='submit':return workspace.submit(body.get('id'),body.get('note',''))
            if action=='review':return workspace.decide(body.get('id'),body.get('decision'),body.get('note',''))
            if action=='connection':return workspace.agent.configure(body)
            if action=='assistant':return workspace.agent.start(body)
            if action=='assistant/cancel':return workspace.agent.cancel(body.get('id'))
            if action=='method':return workspace.save_method(body)
            return JSONResponse({'error':'未知操作'},404)
        except Conflict as e:return JSONResponse({'error':str(e)},409)
        except (ValueError,TypeError,KeyError) as e:return JSONResponse({'error':str(e)[:800]},400)
    @app.get('/')
    def index():return FileResponse(Path(web)/'research.html')
    @app.get('/legacy')
    def legacy():return FileResponse(Path(web)/'index.html')
    @app.get('/prototype')
    def prototype():return RedirectResponse('/assets/prototype-v3/index.html')
    app.mount('/assets',StaticFiles(directory=Path(web)/'assets'),name='assets')
    return app
