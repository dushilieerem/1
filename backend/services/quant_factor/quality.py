"""Advisory quality diagnostics for a frozen factor candidate.

These facts do not replace or relax any admission gate. They make the gap
between "passed the current thresholds" and "credible research evidence"
visible before the mining Agent is judged on factor quality.
"""
from __future__ import annotations

from datetime import date

VERSION = 'quant.factor-quality.v1'
SHORT_SAMPLE_OBSERVATIONS = 120
SHORT_WINDOW_DAYS = 180
HIGH_TURNOVER = 0.30


def _number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _days(start, end):
    try:
        return (date.fromisoformat(str(end)) - date.fromisoformat(str(start))).days + 1
    except (TypeError, ValueError):
        return None


def assess(row: dict) -> dict:
    snapshot = row.get('snapshot') or {}
    request = snapshot.get('request') or {}
    development = (row.get('evidence') or {}).get('development') or {}
    result = development.get('result') or {}
    metrics = result.get('metrics') or {}
    gate = development.get('gate') or {}
    novelty = development.get('novelty') or {}
    checks = gate.get('checks') or []
    observations = next((_number(c.get('actual')) for c in checks if c.get('name') == '有效IC观测数'), None)
    if observations is None:
        observations = _number(result.get('factor_analysis', {}).get('valid_ic_count'))
    costs = {
        'commission_rate': _number(request.get('commission_rate')),
        'stamp_tax': _number(request.get('stamp_tax')),
        'slippage_rate': _number(request.get('slippage_rate')),
        'total_cost': _number(metrics.get('total_cost')),
    }
    turnover = _number(metrics.get('turnover'))
    window_days = _days(request.get('start'), request.get('end'))
    k = gate.get('k_used')
    flags = []
    if all((costs.get(key) or 0) <= 0 for key in ('commission_rate', 'stamp_tax', 'slippage_rate')):
        flags.append({'code': 'zero_cost', 'severity': 'warn', 'message': '回测未设置佣金、印花税或滑点，结果不能视为可交易收益。'})
    if observations is None or observations < SHORT_SAMPLE_OBSERVATIONS:
        flags.append({'code': 'short_sample', 'severity': 'warn', 'message': f'有效 IC 观测少于 {SHORT_SAMPLE_OBSERVATIONS}，跨阶段稳定性证据不足。'})
    if window_days is None or window_days < SHORT_WINDOW_DAYS:
        flags.append({'code': 'short_window', 'severity': 'warn', 'message': f'回测区间不足 {SHORT_WINDOW_DAYS} 天，可能只覆盖单一市场阶段。'})
    if turnover is not None and turnover > HIGH_TURNOVER:
        flags.append({'code': 'high_turnover', 'severity': 'warn', 'message': f'换手率 {turnover:.1%} 偏高，成本敏感性需要单独验证。'})
    if novelty.get('status') not in ('passed', 'skipped_flow_test'):
        flags.append({'code': 'novelty_pending', 'severity': 'warn', 'message': '因子库查重尚未完成或未通过，不能据此认定新因子。'})
    if isinstance(k, int) and k >= 3:
        flags.append({'code': 'multiple_trials', 'severity': 'info', 'message': f'本任务已进行 {k} 次试验，门槛已按 K 校正；仍需注意同任务外的重复搜索。'})
    return {
        'version': VERSION,
        'advisory_only': True,
        'sample': {'observations': observations, 'window_days': window_days, 'k': k, 'symbols': len((request.get('universe_snapshot') or {}).get('symbols') or []) or None},
        'costs': costs,
        'turnover': turnover,
        'novelty': {'status': novelty.get('status'), 'max_abs_correlation': (novelty.get('gate') or {}).get('max_abs_correlation'), 'threshold': (novelty.get('gate') or {}).get('threshold')},
        'flags': flags,
    }
