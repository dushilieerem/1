import sys,os
from pathlib import Path
from urllib.parse import urlparse
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'backend'))
from services.core.env_config import load_env,env
load_env()
os.environ['SVQUANT_TEST_SKIP_SCHEMA_BOOTSTRAP']='1' # Reviewed migrations only, no sample/bootstrap writes.
assert urlparse(env('DATABASE_URL','')).path == '/svquant_dev', 'development database required'
assert env('DEV_SKIP_AUTH','0') == '0', 'authentication must remain enabled'
from services.auth.auth_store import validate_auth_config
validate_auth_config()
os.environ['QUANT_RESEARCH_DURABLE_QUEUE']='1'
# Private RE for this workspace. Keep explicit env if supplied; these defaults
# prevent a manual/BFF restart from silently losing the local compute endpoint.
os.environ.setdefault('QUANT_FACTOR_RE_BASE','http://127.0.0.1:18804')
os.environ.setdefault('QUANT_NOVELTY_RE_BASE','http://127.0.0.1:18804')
from app.main import app
from services.quant_factor.research_queue import start_dispatcher
# Fail startup rather than advertise a healthy but undispatched research queue.
start_dispatcher()
from services.quant_factor.agent_v0 import start_scheduler as start_agent_v0
start_agent_v0()
import uvicorn
# Existing schemas only; avoid unrelated bootstrap seeds, cleanup and migrations.
uvicorn.run(app,host='127.0.0.1',port=18799,lifespan='off',log_level='warning')
