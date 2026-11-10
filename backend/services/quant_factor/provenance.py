"""Fixed method identity for newly frozen research evidence; never backfills history."""
from pathlib import Path
from .policy import digest
from services.core.env_config import env

_FILES=tuple(sorted(path.name for path in Path(__file__).parent.glob('*.py')))
_CODE_REVISION=digest({name:(Path(__file__).parent/name).read_text() for name in _FILES})

def method_manifest(snapshot_hash,executor='human',run_id=None,research_contract=None,method_snapshot=None):
    execution={'snapshot_hash':snapshot_hash,'job_mode':env('QUANT_FACTOR_JOB_MODE','inline') or 'inline','configured_model_alias':env('LLM_MODEL','') or None,'f0_step_limit':12,'development_confirmation_timeout_seconds':900,'sealed_confirmation_timeout_seconds':1800}
    if research_contract:execution.update(research_contract_hash=research_contract['contract_hash'],candidate_warmup_sessions=0)
    if method_snapshot:
        from .research_method import validate_snapshot
        frozen=validate_snapshot(method_snapshot)
        execution.update(method_snapshot=frozen,role_output_limits={role:value['max_output'] for role,value in frozen['roles'].items()})
    return {'method_id':'quant.factor.f0' if executor=='agent' else 'quant.factor.manual',
            'method_version':method_snapshot['method_version'] if executor=='agent' and method_snapshot else 'factor-f0-v1' if executor=='agent' else 'factor-manual-v1',
            'contract_version':'quant.factor.method.v1','code_revision':_CODE_REVISION,
            'config_digest':snapshot_hash,'run_id':run_id,'source_files':list(_FILES),'execution_config':execution,'execution_config_digest':digest(execution)}
