"""Fixed method identity for newly frozen research evidence; never backfills history."""
from pathlib import Path
from .policy import digest
from services.core.env_config import env

_FILES=tuple(sorted(path.name for path in Path(__file__).parent.glob('*.py')))
_CODE_REVISION=digest({name:(Path(__file__).parent/name).read_text() for name in _FILES})

def method_manifest(snapshot_hash,executor='human',run_id=None):
    execution={'snapshot_hash':snapshot_hash,'job_mode':env('QUANT_FACTOR_JOB_MODE','inline') or 'inline','configured_model_alias':env('LLM_MODEL','') or None,'f0_step_limit':12,'development_confirmation_timeout_seconds':900,'sealed_confirmation_timeout_seconds':1800}
    return {'method_id':'quant.factor.f0' if executor=='agent' else 'quant.factor.manual',
            'method_version':'factor-f0-v1' if executor=='agent' else 'factor-manual-v1',
            'contract_version':'quant.factor.method.v1','code_revision':_CODE_REVISION,
            'config_digest':snapshot_hash,'run_id':run_id,'source_files':list(_FILES),'execution_config':execution,'execution_config_digest':digest(execution)}
