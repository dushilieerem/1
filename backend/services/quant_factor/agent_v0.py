"""Minimal v0 autonomous factor-research loop.

This is deliberately smaller than CR-102: one org/user authorization, one
pending proposal, one background research task. It uses existing project/topic/
F0 services and does not create tables or bypass the fixed-data preflight.
"""
from __future__ import annotations

import copy
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from services.core.db import get_conn
from services.core.env_config import env

from . import f0, ledger, resources, service
from .policy import WorkflowError

VERSION = 'agent-v0'
DEFAULT_SYMBOLS = [
    '000001.SZ', '000063.SZ', '000100.SZ', '000333.SZ', '000338.SZ',
    '000568.SZ', '000625.SZ', '000651.SZ', '000725.SZ', '000768.SZ',
    '000776.SZ', '000858.SZ', '000895.SZ', '000938.SZ', '002027.SZ',
    '002049.SZ', '002142.SZ', '002230.SZ', '002415.SZ', '002475.SZ',
    '600000.SH', '600009.SH', '600030.SH', '600031.SH', '600036.SH',
    '600048.SH', '600050.SH', '600104.SH', '600276.SH', '600309.SH',
    '600406.SH', '600438.SH', '600519.SH', '600585.SH', '600690.SH',
    '600703.SH', '600809.SH', '601166.SH', '601318.SH', '601888.SH',
]
HYPOTHESIS = (
    '短周期反转基线：过去 5 个交易日累计收益最低的固定 40 只样本，'
    '次日存在正向反转；仅使用 OHLCV，不改变固定区间与门槛。'
)
_ACCEPTANCE = '方向 Rank IC ≥ 0.005，NW t ≥ t*(K)，有效观测 ≥ 60，最大回撤 ≤ 0.5'

_STATE_PATH = Path(env('QUANT_AGENT_V0_STATE', '') or (
    Path(__file__).resolve().parents[3] / 'institutional-workflow/runtime/agent-v0.json'
))
_AUDIT_PATH = Path(env('QUANT_AGENT_V0_AUDIT')) if env('QUANT_AGENT_V0_AUDIT') else None
_STATE_LOCK = threading.RLock()
_TICK_LOCK = threading.Lock()


def _audit(action: str, **fields) -> None:
    """Append-only local audit trail for who enabled/started what.

    v0 has no DDL; this file is the durable record until CR-102 events land.
    """
    event = {'at': _now(), 'action': action, **fields}
    path = _AUDIT_PATH or _STATE_PATH.with_name('agent-v0-audit.jsonl')
    with _STATE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_state() -> dict:
    with _STATE_LOCK:
        try:
            value = json.loads(_STATE_PATH.read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}


def _write_state(state: dict) -> None:
    with _STATE_LOCK:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_PATH.with_suffix('.tmp')
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8')
        os.replace(tmp, _STATE_PATH)


def _update_state(**changes) -> dict:
    state = _read_state()
    state.update(changes)
    state['updated_at'] = _now()
    _write_state(state)
    return state


def enabled() -> bool:
    return env('QUANT_AGENT_V0_ENABLED', '1') == '1'


def _public_state(uid: int, org: int, *, can_control: bool = False) -> dict:
    state = _read_state()
    same_owner = bool(state.get('enabled')) and int(state.get('user_id') or 0) == int(uid) and int(state.get('org_id') or 0) == int(org)
    control = service.control_status(uid, org)
    paused = bool(control.get('paused'))
    with get_conn() as c:
        active = c.execute(
            "SELECT id,topic_id,status,decision,updated_at FROM quant_factor_f0_runs "
            "WHERE org_id=%s AND status IN ('queued','running') ORDER BY created_at DESC LIMIT 1",
            (org,),
        ).fetchone()
        pending = _pending_project(c, uid)
        topic = None
        if pending:
            topic = c.execute(
                'SELECT id,status,view_id FROM quant_factor_topics WHERE user_id=%s AND project_id=%s LIMIT 1',
                (uid, pending['id']),
            ).fetchone()
    if not enabled():
        status = 'not_enabled'
        reason = '自主研究功能未开启。'
    elif not same_owner:
        status = 'not_enabled'
        reason = '自主研究尚未由当前账号开启。'
    elif paused:
        status = 'paused'
        reason = '全局调度已暂停，不启动新的自动研究。'
    elif active:
        status = 'running'
        reason = '已有研究在运行；同一时间只推进 1 项。'
    elif pending and topic:
        status = 'waiting_data' if state.get('last_state') == 'waiting_data' else 'pending_start'
        reason = (state.get('last_error') if status == 'waiting_data' else '') or 'Agent 已起草任务，等待启动。'
    elif pending:
        status = 'waiting_data' if state.get('last_state') == 'waiting_data' else 'drafting'
        reason = state.get('last_error') or 'Agent 已起草任务，等待固定数据。'
    else:
        status = 'idle'
        reason = '等待下一次选题触发。'
    return {
        'available': True,
        'mode': VERSION,
        'enabled': bool(enabled() and same_owner),
        'state': status,
        'reason': reason,
        'paused': paused,
        'active_run': dict(active) if active else None,
        'pending': {
            'project_id': pending['id'],
            'name': pending['name'],
            'topic_id': topic['id'] if topic else None,
            'topic_status': topic['status'] if topic else None,
        } if pending else None,
        'last_tick_at': state.get('last_tick_at'),
        'last_error': state.get('last_error') or '',
        'updated_at': state.get('updated_at'),
        'can_control': bool(can_control),
    }


def status(uid: int, org: int, *, can_control: bool = False) -> dict:
    return _public_state(uid, org, can_control=can_control)


def _pending_project(c, uid: int):
    return c.execute(
        "SELECT id,name,config,created_at FROM detect_projects "
        "WHERE user_id=%s AND config ? 'agentV0' ORDER BY created_at DESC LIMIT 1",
        (uid,),
    ).fetchone()


def _project(uid: int, project_id: str) -> dict:
    from services.factor.detect_store import get_project
    return get_project(uid, project_id)['project']


def _baseline_config() -> dict:
    from services.factor.detect_store import _default_config
    cfg = _default_config([])
    cfg.update({
        'customCombine': 'def combo_factor(self):\n    """自定义组合"""\n    return -self.close.pct_change(5)',
        'universe': 'CSI500',
        'benchmark': 'CSI500',
        'rangeMode': 'custom',
        'startDate': '2025-07-01',
        'endDate': '2025-09-30',
        'analysisLevel': 'core',
        'rebalanceDays': 1,
        'executionTiming': 'next_close',
        'researchUniverseSymbols': list(DEFAULT_SYMBOLS),
        'researchPlan': {
            'rules': {
                'icMetric': 'rank_ic', 'direction': 'positive',
                'maxDrawdown': 0.5, 'minSignedIc': 0.005, 'minObservations': 60,
            },
            'target': '未来1个交易日收益',
            'revision': 'agent-v0-' + str(uuid.uuid4()),
            'frequency': 'daily',
            'maxTrials': 2,
            'acceptance': _ACCEPTANCE,
            'hypothesis': HYPOTHESIS,
            'validationEnd': '2026-09-21',
            'developmentEnd': '2025-09-30',
            'researchPurpose': 'discovery',
            'validationStart': '2026-06-22',
            'developmentStart': '2025-07-01',
            'fieldRestriction': 'ohlcv',
            'improvementScope': '只改进实现，不改变经济假设和方向',
            'candidateExpression': '',
        },
        'researchContext': {
            'question': HYPOTHESIS,
            'direction': 'agent-v0',
            'background': '后端 Agent v0 自主起草；单并发、固定 40 只、固定视图、2 次研发/1 次封存。',
        },
        'agentV0': {
            'version': VERSION,
            'state': 'draft',
            'familyId': str(uuid.uuid4()),
            'createdAt': _now(),
            'direction': 'short-term reversal',
            'maxTasks': 1,
            'createdBy': 'agent-v0',
        },
    })
    return cfg


def _create_baseline_project(uid: int, org: int) -> dict:
    from services.factor.detect_store import upsert_project
    name = 'Agent 自主研究：短周期反转基线 · ' + datetime.now().strftime('%m%d')
    payload = {
        'id': str(uuid.uuid4()),
        'name': name,
        'factorName': 'custom_combo',
        'description': HYPOTHESIS,
        'config': _baseline_config(),
        'sample': False,
    }
    project = upsert_project(uid, payload)['project']
    _audit('drafted', user_id=uid, org_id=org, project_id=project['id'], name=project['name'])
    return project


def _topic_payload(view: dict) -> dict:
    dates = [d.get('date_max') for d in (view.get('datasets') or {}).values() if d.get('date_max')]
    return {
        'view_id': view['view_id'],
        'release_id': '',
        'release_ids': {k: d.get('release') for k, d in (view.get('datasets') or {}).items() if d.get('release')},
        'view_manifest_sha256': view.get('manifest_sha256') or '',
        'contract_revision': view.get('contract_revision') or '',
        'as_of': max(dates) if dates else None,
        'development_start': '2025-07-01',
        'development_end': '2025-09-30',
        'validation_start': '2026-06-22',
        'validation_end': '2026-09-21',
        'primary_holding_period': 1,
        'policy_version': 'v5-p0',
        'max_trials': 2,
        'max_sealed': 1,
    }


def _preflight(uid: int, org: int, project: dict):
    """Return (view, None) only when the fixed-data gate allows a real run."""
    from services.workflow_workspace.platform_data import published_view
    from .research_contract import from_project
    try:
        view = published_view()
        plan = copy.deepcopy((project.get('config') or {}).get('researchPlan') or {})
        contract = from_project(uid, org, project, view)
        plan['researchContract'] = contract
        candidate = {**(project.get('config') or {}), 'researchPlan': plan}
        receipt = resources.config_preflight(candidate)
    except (ValueError, WorkflowError, KeyError) as exc:
        return None, str(exc)
    if not receipt.get('allowed'):
        return None, '；'.join(receipt.get('reasons') or ['固定数据预检未通过'])
    return view, None


def _start_pending(uid: int, org: int, project: dict, state: dict) -> dict:
    view, error = _preflight(uid, org, project)
    if error:
        _update_state(last_state='waiting_data', last_error=error, last_tick_at=_now())
        return {'state': 'waiting_data', 'reason': error}
    with get_conn() as c:
        topic = c.execute(
            'SELECT id,status FROM quant_factor_topics WHERE user_id=%s AND project_id=%s LIMIT 1',
            (uid, project['id']),
        ).fetchone()
    if not topic:
        try:
            topic = ledger.create_topic(uid, org, project['id'], _topic_payload(view))
            topic = topic['topic'] if isinstance(topic, dict) and 'topic' in topic else topic
        except (ValueError, WorkflowError, KeyError) as exc:
            _update_state(last_state='waiting_data', last_error=str(exc), last_tick_at=_now())
            return {'state': 'waiting_data', 'reason': str(exc)}
    with get_conn() as c:
        branch = c.execute(
            'SELECT id FROM quant_factor_branches WHERE user_id=%s AND org_id=%s AND topic_id=%s ORDER BY created_at,id LIMIT 1',
            (uid, org, topic['id']),
        ).fetchone()
    if not branch:
        error = '任务首分支尚未就绪，未启动。'
        _update_state(last_state='waiting_data', last_error=error, last_tick_at=_now())
        return {'state': 'waiting_data', 'reason': error}
    try:
        run = f0.start(uid, org, topic['id'], branch['id'], 'agent-v0:' + topic['id'])
    except (ValueError, WorkflowError, KeyError) as exc:
        _update_state(last_state='waiting_data', last_error=str(exc), last_tick_at=_now())
        return {'state': 'waiting_data', 'reason': str(exc)}
    if run.get('status') == 'stopped':
        error = run.get('stop_reason') or run.get('reason') or '启动未完成。'
        _update_state(last_state='waiting_data', last_error=error, last_tick_at=_now())
        return {'state': 'waiting_data', 'reason': error}
    marker = dict((project.get('config') or {}).get('agentV0') or {})
    marker.update(state='started', version=VERSION, topicId=topic['id'], startedAt=_now())
    with get_conn() as c:
        # Only touch the agent marker; create_topic just wrote the frozen
        # researchContract/v5 control fields into the same config.
        c.execute(
            "UPDATE detect_projects SET config=jsonb_set(config,'{agentV0}',%s::jsonb,true),updated_at=NOW() "
            'WHERE user_id=%s AND id=%s',
            (json.dumps(marker, ensure_ascii=False), uid, project['id']),
        )
    _update_state(last_state='running', last_error='', last_tick_at=_now(), active_topic_id=topic['id'])
    _audit('started', user_id=uid, org_id=org, project_id=project['id'], topic_id=topic['id'], run_id=run.get('id'))
    return {'state': 'running', 'run': run}


def tick(uid: int, org: int) -> dict:
    if not enabled():
        return {'state': 'not_enabled', 'reason': '自主研究功能未开启。'}
    state = _read_state()
    if not state.get('enabled') or int(state.get('user_id') or 0) != int(uid) or int(state.get('org_id') or 0) != int(org):
        return {'state': 'not_enabled', 'reason': '自主研究尚未由当前账号开启。'}
    if service.control_status(uid, org).get('paused'):
        _update_state(last_state='paused', last_tick_at=_now())
        return {'state': 'paused', 'reason': '全局调度已暂停。'}
    with _TICK_LOCK:
        with get_conn() as c:
            active = c.execute(
                "SELECT id FROM quant_factor_f0_runs WHERE org_id=%s AND status IN ('queued','running') LIMIT 1",
                (org,),
            ).fetchone()
            pending = _pending_project(c, uid)
        if active:
            _update_state(last_state='running', last_tick_at=_now())
            return {'state': 'running', 'reason': '已有研究在运行；同一时间只推进 1 项。'}
        project = _project(uid, pending['id']) if pending else _create_baseline_project(uid, org)
        return _start_pending(uid, org, project, state)


def enable(uid: int, org: int) -> dict:
    state = {
        'enabled': True,
        'version': VERSION,
        'user_id': int(uid),
        'org_id': int(org),
        'enabled_at': _now(),
        'last_state': 'idle',
        'last_error': '',
    }
    _write_state(state)
    _audit('enabled', user_id=uid, org_id=org)
    try:
        tick(uid, org)
    except Exception as exc:  # keep the switch on; surface the reason in status
        _update_state(last_state='error', last_error=str(exc), last_tick_at=_now())
    return status(uid, org, can_control=True)


def disable(uid: int, org: int) -> dict:
    state = _read_state()
    if state and int(state.get('user_id') or 0) == int(uid) and int(state.get('org_id') or 0) == int(org):
        state['enabled'] = False
        state['disabled_at'] = _now()
        state['last_state'] = 'disabled'
        _write_state(state)
        _audit('disabled', user_id=uid, org_id=org)
    return status(uid, org, can_control=True)


def start_scheduler(interval: int = 20) -> None:
    def loop():
        while True:
            time.sleep(interval)
            try:
                state = _read_state()
                if state.get('enabled') and state.get('user_id') and state.get('org_id'):
                    tick(int(state['user_id']), int(state['org_id']))
            except Exception as exc:
                try:
                    _update_state(last_state='error', last_error=str(exc), last_tick_at=_now())
                except Exception:
                    pass
    threading.Thread(target=loop, name='quant-agent-v0', daemon=True).start()
