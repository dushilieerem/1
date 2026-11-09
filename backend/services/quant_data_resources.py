"""M5 read-only data resources: catalogue, view lineage, quality and requests."""
from __future__ import annotations

import json
import os
import uuid

import yaml
from datetime import datetime, timezone
from pathlib import Path

from services.core.db import get_conn

DATA_HOME = Path(os.environ.get("SVQUANT_DATA_HOME") or "/home/dev01/project/svquant-data")

KNOWN_LIMITS = {
    "industry_membership_history": ["申万官方生效日 + 当前 vintage，可能被后续修订覆盖，不是无修订 PIT"],
    "industry_daily": ["latest_only；历史回测不要使用"],
    "index_membership": ["000300/000905 有历史权重；399317/399101/399303 仅最新快照；399303 confidence=medium；000015 仅 2026-09-30 起锚点"],
    "valuation_daily": ["pe_ttm 有前视；回测用 pe_ttm_pit；2026-10-08 后 carry-forward；total_mv 为真总市值"],
    "fund_flow_daily": ["东财口径；close/change_pct 为观察日回溯复权，不能算收益"],
    "fund_flow_candidate": ["东财口径；close/change_pct 为观察日回溯复权，不能算收益"],
    "analyst_consensus_snapshot": ["仅当前快照（forward-only），没有历史"],
    "us_fundamentals_sec": ["单位混用；跨公司比较需过滤 unit='USD'"],
}


def _read_json(rel: str):
    path = (DATA_HOME / rel).resolve()
    if not path.is_relative_to(DATA_HOME.resolve()):
        raise ValueError("数据目录越界")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _current_view():
    link = DATA_HOME / "views" / "current"
    target = Path(os.path.realpath(link))
    view_id = target.parent.name if target.name == "materialized" else target.name
    return view_id, target


FREQUENCY = {
    "minute_bars": "1 分钟",
    "daily_bars": "日频", "daily_bars_unadjusted": "日频", "ifind_daily_bars_unadjusted": "日频",
    "etf_daily": "日频", "us_stock_quotes_bfq": "日频", "us_stock_quotes_hfq": "日频",
    "valuation": "日频", "valuation_daily": "日频", "ifind_valuation": "日频",
    "index_price": "日频", "ifind_index_price": "日频", "index_weights": "日频",
    "ifind_index_weights": "日频", "index_membership": "日频（成分按公告）",
    "industry_daily": "日频", "industry_membership_history": "日频（历史生效日）",
    "security_status_daily": "日频", "limit_prices": "日频", "margin_daily": "日频",
    "fund_flow_daily": "日频", "fund_flow_candidate": "日频", "northbound_flow_daily": "日频",
    "northbound_holdings_quarterly": "季度", "risk_daily": "日频",
    "calendar": "日历", "us_stock_calendar": "日历", "ifind_calendar": "日历",
    "news": "日更", "us_stock": "快照", "us_stock_snapshot": "快照",
    "security_master": "快照", "ifind_security_master": "快照",
    "us_stock_universe": "快照", "universe": "快照",
    "analyst_consensus_snapshot": "快照",
    "financial_balance": "报告期/公告日", "financial_cashflow": "报告期/公告日",
    "financial_income": "报告期/公告日", "free_financial_income": "报告期/公告日",
    "per_share": "报告期/公告日", "pershare_index": "报告期/公告日",
    "holder_num": "报告期/公告日", "capital": "公告日", "dividend_actions": "公告日",
    "buyback_plan": "公告日", "buyback_execution": "公告日",
    "industry_code_map": "快照", "sector_concept": "快照",
    "us_fundamentals_sec": "报告期/公告日",
}


_VIEW_CACHE: dict[str, tuple[int, dict]] = {}


def _view_yaml(view_id: str) -> dict:
    # Prefer the materialized artifact; a definition-only YAML is not a release.
    candidates = [
        DATA_HOME / "views" / view_id / "materialized" / "view.yaml",
        DATA_HOME / "views" / f"{view_id}.yaml",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        mtime = path.stat().st_mtime_ns
        cached = _VIEW_CACHE.get(view_id)
        if cached and cached[0] == mtime:
            return cached[1]
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        _VIEW_CACHE[view_id] = (mtime, data)
        return data
    return {}


def _published_views() -> set[str]:
    """Actual releases: materialized dir with manifest and matching VIEW_ID."""
    out: set[str] = set()
    root = DATA_HOME / "views"
    for path in root.iterdir() if root.is_dir() else []:
        materialized = path / "materialized"
        manifest = materialized / "manifest.json"
        marker = materialized / "VIEW_ID"
        if not (path.is_dir() and manifest.is_file() and marker.is_file()):
            continue
        try:
            if marker.read_text(encoding="utf-8").strip() == path.name:
                out.add(path.name)
        except OSError:
            continue
    return out


def _published_view_paths() -> dict[str, Path]:
    return {vid: DATA_HOME / "views" / vid / "materialized" for vid in _published_views()}


def _pit_label(rule: str) -> str:
    rule = str(rule or '').strip()
    if rule == 'date <= as_of':return '按日期过滤（不代表历史时点保证）'
    if rule == 'latest_only':return '仅最新快照'
    if rule in ('announce_date <= as_of','m_anntime <= as_of','announce <= as_of'):return '按公告日过滤'
    return rule or '时点口径待确认'


class MetadataUnavailable(RuntimeError):pass


def _metadata():
    """Read bounded release/catalogue metadata only; never read market tables."""
    view_id,target=_current_view()
    try:monitor=_read_json('docs/monitor-data.json')
    except (OSError,ValueError):raise MetadataUnavailable('数据目录读取失败，请稍后重试') from None
    if not isinstance(monitor,dict) or not isinstance(monitor.get('datasets'),list) or any(not isinstance(x,dict) or not isinstance(x.get('name'),str) for x in monitor['datasets']):raise MetadataUnavailable('数据目录格式无法核对，请稍后重试')
    publication_error='';manifest={};contract={};definition={}
    try:
        manifest=json.loads((target/'manifest.json').read_text())
        if not isinstance(manifest,dict) or not isinstance(manifest.get('datasets'),dict) or not isinstance(manifest.get('contract_version'),str) or any(not isinstance(e,dict) for e in manifest['datasets'].values()) or manifest.get('view_id')!=view_id or (target/'VIEW_ID').read_text().strip()!=view_id:
            raise ValueError('发布标识与版本不一致')
    except (OSError,ValueError):publication_error='发布版本依据无法核对';manifest={}
    try:
        contract=yaml.safe_load((target/'data_contract.yaml').read_text()) or {}
        if not isinstance(contract,dict) or not isinstance(contract.get('datasets'),dict) or contract.get('contract_version')!=manifest.get('contract_version'):
            contract={}
    except (OSError,ValueError,yaml.YAMLError):pass
    try:
        definition=yaml.safe_load((target/'view.yaml').read_text()) or {}
        if not isinstance(definition,dict) or definition.get('view_id')!=view_id or not isinstance(definition.get('datasets'),dict):definition={}
    except (OSError,ValueError,yaml.YAMLError):pass
    quality={};quality_error=''
    try:
        quality=_read_json(f'ops/quality/{view_id}.json')
        if not isinstance(quality,dict) or not isinstance(quality.get('datasets'),dict):quality={};quality_error='检查结果格式无法核对'
        elif quality.get('view_id')!=view_id:quality={};quality_error='检查结果与当前版本不一致'
    except FileNotFoundError:quality_error='检查结果文件缺失，当前检查状态待确认'
    except (OSError,ValueError):quality_error='检查结果读取失败'
    if _current_view()[0]!=view_id:raise ValueError('发布版本已更新，请重新读取目录')
    return {'view_id':view_id,'target':target,'monitor':monitor,'manifest':manifest,'contract':contract,
            'publication_error':publication_error,'definition':definition,'quality':quality,'quality_error':quality_error,
            'catalog_matches':monitor.get('view_id')==view_id}


def _member_publication(meta,entry,name):
    view=meta['view_id'];manifest=meta['manifest']
    published=None;publication_reason=meta['publication_error']
    if manifest:
        if not entry:published=False;publication_reason='不在该发布版本内'
        elif not isinstance(entry.get('path'),str) or not isinstance(entry.get('release'),str) or not entry.get('release') or '/' in entry['release'] or '\\' in entry['release'] or entry['release'] in ('.','..') or not isinstance(entry.get('sha256'),str) or len(entry['sha256'])!=64:
            publication_reason='发布成员身份字段不完整'
        else:
            defined=(meta['definition'].get('datasets') or {}).get(name) or {}
            if not isinstance(defined,dict) or defined.get('release')!=entry.get('release') or defined.get('sha256')!=entry.get('sha256'):
                return None,'发布清单与固定版本定义身份不一致'
            rel=Path(str(entry.get('path') or ''))
            if rel.is_absolute() or '..' in rel.parts or not rel.parts:
                publication_reason='物化路径依据不完整'
            else:
                candidate=meta['target']/rel;resolved=candidate.resolve();safe=resolved.is_relative_to(meta['target'].resolve())
                if not safe:
                    pinned=(DATA_HOME/str(entry.get('kind') or '')/'releases'/str(entry.get('release') or '')).resolve()
                    defined=(meta['definition'].get('datasets') or {}).get(name) or {}
                    safe=bool(entry.get('kind') in ('free','ifind','derived') and pinned.is_relative_to(DATA_HOME.resolve()) and entry.get('release') and isinstance(defined,dict) and resolved.is_relative_to(pinned) and resolved==Path(str(entry.get('source') or '')).resolve() and defined.get('release')==entry.get('release') and (Path(str(defined.get('root') or ''))/str(defined.get('path') or '')).resolve()==resolved)
                if not safe:publication_reason='发布路径未通过固定版本来源核验'
                elif candidate.is_file() and candidate.suffix=='.parquet':published=True
                elif candidate.is_dir() and type(entry.get('files')) is int and entry['files']>0 and next(candidate.iterdir(),None) is not None:published=True
                else:published=False;publication_reason='该版本尚无可用发布文件'
    return published,publication_reason


def _dataset_metadata(meta,item):
    name=item['name'];view=meta['view_id'];manifest=meta['manifest'];entry=(manifest.get('datasets') or {}).get(name)
    contract=(meta['contract'].get('datasets') or {}).get(name) or {}
    if not isinstance(contract,dict) or not isinstance(contract.get('units',{}),dict) or not isinstance(contract.get('fields',[]),list) or any(not isinstance(x,str) for x in contract.get('fields',[])) or any(not isinstance(v,str) for v in contract.get('units',{}).values()) or any(contract.get(k) is not None and not isinstance(contract.get(k),str) for k in ('historical_use','sw_pit_rule','notes','code_system','null_semantics')):contract={}
    source_ref=f'{view}/data_contract.yaml#{name}'
    published,publication_reason=_member_publication(meta,entry,name)
    same=meta['catalog_matches']
    contract_matches=False
    if entry and contract and contract.get('sha256') and contract.get('sha256')==entry.get('sha256') and isinstance(contract.get('path'),str):
        crel=Path(contract['path']);cpath=meta['target']/crel;dpath=meta['target']/str(entry.get('path') or '')
        formats={'date_partitioned','long_partitioned','long_table','mixed_dir','parquet_file','per_index_file','per_symbol_parquet','wide_multiindex','wide_multiindex_per_file','wide_per_index_file','wide_symbol_matrix'}
        format_ok=contract.get('format') in formats and (cpath.is_dir() or (cpath.is_file() and contract.get('format') in ('parquet_file','wide_multiindex')))
        contract_matches=format_ok and not crel.is_absolute() and '..' not in crel.parts and (cpath.resolve()==dpath.resolve() or (dpath.is_dir() and cpath.resolve().is_relative_to(dpath.resolve()))) and cpath.exists()

    if not contract_matches:contract={}
    fields_valid=same and isinstance(item.get('fields'),list) and all(isinstance(f,dict) and isinstance(f.get('name'),str) and all(f.get(k) is None or isinstance(f.get(k),str) for k in ('label','note','unit','start','end')) for f in item['fields'])
    raw_fields=item.get('fields',[]) if fields_valid else []
    fields=[];availability=[]
    rule=(entry or {}).get('pit_rule') or '';rule=rule if isinstance(rule,str) else '';sw_rule=contract.get('sw_pit_rule') or ''
    sw_latest=sw_rule in ('latest_only','latest_only（历史行业轮动一律用 industry_membership_history）')
    for raw in raw_fields:
        field=dict(raw);fname=field.get('name','');field['catalog_unit']=field.get('unit') or '';field['unit']=(contract.get('units') or {}).get(fname) or field.get('unit') or '';status='unknown';basis='字段适用性待确认';note=field.get('note') or ''
        if name=='industry_daily' and fname in ('sw_l1_code','sw_l1_name','sw_l2_code','sw_l2_name') and sw_latest:
            status='latest_only';basis='仅最新分类快照';note=contract.get('historical_use') or contract.get('null_semantics') or note
        elif rule=='latest_only' and contract_matches:
            status='latest_only';basis='仅最新快照'
        elif contract_matches and rule:
            basis=_pit_label(rule)+'；字段适用性待确认'
        catalog_note=field.get('note') or ''
        conflict=name=='industry_daily' and fname in ('sw_l2_code','sw_l2_name') and catalog_note in ('申万二级代码；当前暂为 null。','申万二级名称；当前暂为 null。') and sw_latest
        if conflict:status='conflict';basis='当前分类快照；字段覆盖状态待确认'
        field.update(availability_status=status,availability_rule=basis,availability_note=note,catalog_note=catalog_note,catalog_source_ref=str(meta['monitor'].get('view_id') or 'unknown')+'/monitor-data#'+fname,source_ref=source_ref if contract_matches else f'{view}/monitor-data#'+fname)
        fields.append(field);availability.append({k:field[k] for k in ('name','availability_status','availability_rule','availability_note','source_ref')})
    limits=list(KNOWN_LIMITS.get(name,[]))
    for key in ('historical_use','sw_pit_rule'):
        if contract.get(key) and contract[key] not in limits:limits.append(contract[key])
    # These are source statements, not inferred historical fitness decisions.
    if name=='minute_bars' and same and isinstance(item.get('desc'),str) and item.get('desc'):limits.append(item['desc'])
    if not fields_valid:limits.append('字段目录缺失或格式无法核对，字段适用性待确认')
    if not same:limits.append('目录说明与发布版本不一致，覆盖和字段信息待重新核对')
    if not contract_matches:limits.append('缺少与此发布版本一致的字段适用性契约')
    if entry and (not entry.get('date_min') or not entry.get('date_max')):limits.append('发布记录未确认覆盖区间；目录或契约中的日期不能替代实际覆盖验证')
    status='restricted' if limits or rule=='latest_only' else 'timing' if rule and contract_matches else 'unknown'
    if not same:status='unknown'
    q=(meta['quality'].get('datasets') or {}).get(name) or {}
    q_error=meta['quality_error']
    if not isinstance(q,dict) or (bool(q) and ('ok' not in q or 'results' not in q)) or (q.get('ok') is not None and type(q.get('ok')) is not bool) or not isinstance(q.get('results',[]),list) or any(not isinstance(x,dict) or type(x.get('ok')) is not bool or not isinstance(x.get('message'),str) for x in q.get('results',[])):
        q={};q_error='该数据集检查结果格式无法核对'
    quality_status='error' if q_error else 'passed' if q.get('ok') is True else 'warning' if q.get('ok') is False else 'unchecked'
    return {'name':name,'label':item.get('label') if isinstance(item.get('label'),str) and item.get('label') else name,'topic':item.get('topic') if isinstance(item.get('topic'),str) else '未分类','source':item.get('source') if isinstance(item.get('source'),str) else '',
            'provenance':item.get('provenance') if isinstance(item.get('provenance'),str) else '', 'description':item.get('desc') if same and isinstance(item.get('desc'),str) else '',
            'rows':entry.get('rows') if published and type(entry.get('rows')) is int else None,'start':entry.get('date_min') if entry and isinstance(entry.get('date_min'),str) else None,
            'end':entry.get('date_max') if entry and isinstance(entry.get('date_max'),str) else None,'coverage_sources':{'published':{'start':(entry or {}).get('date_min'),'end':(entry or {}).get('date_max')},'catalog':{'start':item.get('start') if same else None,'end':item.get('end') if same else None},'contract':contract.get('coverage') or {}},'updated':(entry or {}).get('created_at') or '',
            'field_count':len(fields) if fields_valid else None,'fields':fields,'field_index':[{'name':f.get('name'),'label':f.get('label')} for f in fields],
            'frequency':FREQUENCY.get(name,'待确认'),'release':(entry or {}).get('release') or '',
            'pit_rule':rule,'pit_label':_pit_label(rule),'batch_created_at':(entry or {}).get('created_at') or '',
            'published':published,'publication_status':'published' if published is True else 'unpublished' if published is False else 'unknown',
            'publication_note':publication_reason,'publication_version':view if published is True else None,
            'catalog_version':meta['monitor'].get('view_id'),'quality_version':meta['quality'].get('view_id'),
            'quality_ok':q.get('ok') if quality_status not in ('error','unchecked') else None,
            'quality_status':quality_status,'quality_note':q_error,'quality_checks':q.get('results') or [] if not q_error else [],
            'limitations':limits,'applicability':{'status':status,'summary':'；'.join(limits) or (_pit_label(rule)+'；具体研究用途仍需核对字段、股票范围和区间'),
              'assessed_fields':[f['name'] for f in availability if f['availability_status']!='unknown'],
              'evidence_refs':[source_ref] if contract_matches else [],'evidence_status':'matched' if contract_matches and same else 'unknown','is_research_authorization':False},
            'field_availability':availability,'contract_details':{k:contract[k] for k in ('contract_version','code_system','null_semantics','notes','historical_use','sw_pit_rule') if k in contract}}


def catalogue(uid: int, org: int, all_members: bool = False):
    meta=_metadata();view_id=meta['view_id']
    with get_conn() as c:
        factor_where,factor_params='org_id=%s AND view_id=%s',[org,view_id]
        strategy_where,strategy_params='org_id=%s AND view_id=%s',[org,view_id]
        if not all_members:
            factor_where+=' AND user_id=%s';factor_params.append(uid)
            strategy_where+=' AND user_id=%s';strategy_params.append(uid)
        factor_locked=c.execute(f'SELECT COUNT(*) AS n FROM quant_factor_topics WHERE {factor_where}',tuple(factor_params)).fetchone()['n']
        strategy_locked=c.execute(f'SELECT COUNT(*) AS n FROM strategy_topics WHERE {strategy_where}',tuple(strategy_params)).fetchone()['n']
    items={x['name']:x for x in meta['monitor'].get('datasets') or []}
    for name in meta['manifest'].get('datasets') or {}:items.setdefault(name,{'name':name})
    datasets=[_dataset_metadata(meta,item) for item in items.values()]
    for item in datasets:item.pop('fields',None);item.pop('field_availability',None);item.pop('contract_details',None)
    released=[x for x in datasets if x['published'] is True]
    counts={key:sum(x['quality_status']==key for x in released) for key in ('passed','warning','unchecked','error')}
    return {'view_id':view_id,'generated_at':meta['monitor'].get('generated_at'),'catalog_version':meta['monitor'].get('view_id'),
        'summary':{'datasets':len(released),'catalog_datasets':len(datasets),'rows':sum(x['rows'] for x in released) if all(isinstance(x['rows'],int) for x in released) else None,'fields':sum(x['field_count'] for x in released) if all(isinstance(x['field_count'],int) for x in released) else None,'restricted':sum(x['applicability']['status']=='restricted' for x in released)},
        'quality_checked_at':meta['quality'].get('checked_at'),'quality_ok':meta['quality'].get('ok'),
        'quality_summary':{'checked':counts['passed']+counts['warning'],'passed':counts['passed'],'failed':counts['warning'],'unchecked':counts['unchecked'],'errors':counts['error'],'total':len(released)},
        'locked_by':{'factor_topics':factor_locked,'strategy_topics':strategy_locked},'datasets':datasets}


def dataset(uid: int, org: int, name: str, view_id: str|None = None):
    if view_id and view_id not in _published_views():raise KeyError(view_id)
    meta=_metadata()
    if view_id and view_id!=meta['view_id']:raise ValueError('目录版本已更新，请关闭详情并重新读取目录')
    item=next((x for x in meta['monitor'].get('datasets') or [] if x.get('name')==name),None)
    if not item and name in (meta['manifest'].get('datasets') or {}):item={'name':name}
    if not item:raise KeyError(name)
    out=_dataset_metadata(meta,item);out['view_id']=meta['view_id'];return out


def _available_delivery_views():
    """Only this data UI/delivery check; do not alter research locked-view lookup."""
    available={}
    for vid,target in _published_view_paths().items():
        try:
            manifest=json.loads((target/'manifest.json').read_text());definition=yaml.safe_load((target/'view.yaml').read_text())
            if not isinstance(manifest,dict) or manifest.get('view_id')!=vid or not isinstance(manifest.get('datasets'),dict) or not manifest['datasets'] or not isinstance(definition,dict) or not isinstance(definition.get('datasets'),dict) or definition.get('view_id')!=vid:continue
            meta={'view_id':vid,'target':target,'manifest':manifest,'definition':definition,'publication_error':''}
            if all(isinstance(e,dict) and _member_publication(meta,e,name)[0] is True for name,e in manifest['datasets'].items()):available[vid]=target
        except (OSError,ValueError,yaml.YAMLError):continue
    return available


def views(uid: int, org: int):
    current, _ = _current_view()
    rows = []
    for vid, path in sorted(_available_delivery_views().items(), key=lambda kv: kv[1].stat().st_mtime, reverse=True):
        meta = _view_yaml(vid)
        rows.append({
            "view_id": vid, "current": vid == current,
            "published_at": (json.loads((path/"manifest.json").read_text()).get("published_at") or None),
            "created_at": meta.get("created_at") or "",
            "contract_version": meta.get("contract_version") or "",
            "dataset_count": len(meta.get("datasets") or {}),
        })
    return {"current": current, "views": rows}


def view_usage(uid: int, org: int, view_id: str, all_members: bool = False):
    if view_id not in _published_views():
        raise KeyError(view_id)
    factor_where, factor_params = "t.org_id=%s AND t.view_id=%s", [org, view_id]
    strategy_where, strategy_params = "org_id=%s AND view_id=%s", [org, view_id]
    if not all_members:
        factor_where += " AND t.user_id=%s"
        factor_params.append(uid)
        strategy_where += " AND user_id=%s"
        strategy_params.append(uid)
    with get_conn() as c:
        factors = [dict(r) for r in c.execute(
            f"""SELECT t.id,t.display_no,t.project_id,t.user_id,p.name AS project_name
               FROM quant_factor_topics t
               JOIN detect_projects p ON p.user_id=t.user_id AND p.id=t.project_id
               WHERE {factor_where}
               ORDER BY t.display_no""", tuple(factor_params)).fetchall()]
        strategies = [dict(r) for r in c.execute(
            f"""SELECT id,display_no,name,user_id FROM strategy_topics
               WHERE {strategy_where} ORDER BY display_no""",
            tuple(strategy_params)).fetchall()]
    return {
        "view_id": view_id,
        "factor_topics": [{"id": r["id"], "label": f"T{r['display_no']}", "name": r["project_name"]} for r in factors],
        "strategy_topics": [{"id": r["id"], "label": f"S{r['display_no']}", "name": r["name"]} for r in strategies],
    }


RELATED_TABLES = {
    "factor_topic": "quant_factor_topics",
    "strategy_topic": "strategy_topics",
    "portfolio_plan": "portfolio_plans",
}
TRANSITIONS = {
    "submitted": {"in_progress", "delivered", "unsupported"},
    "in_progress": {"delivered", "unsupported"},
    "delivered": set(),
    "unsupported": set(),
}


def _related(uid: int, org: int, related_type: str, related_id: str) -> bool:
    table = RELATED_TABLES.get(related_type)
    if not table or not related_id:
        return False
    with get_conn() as c:
        row = c.execute(
            f"SELECT 1 FROM {table} WHERE id=%s AND user_id=%s AND org_id=%s",
            (related_id, uid, org)).fetchone()
    return bool(row)


def list_requests(uid: int, org: int, all_members: bool = False):
    """Member-private by default; research managers see the whole org for handling."""
    where, params = "r.org_id=%s", [org]
    if not all_members:
        where += " AND r.user_id=%s"
        params.append(uid)
    with get_conn() as c:
        rows = c.execute(
            f"""SELECT r.id,r.title,r.purpose,r.period,r.frequency,r.fields,r.related_type,
                      r.related_id,r.delivered_view,r.status,r.note,r.handled_at,
                      r.created_at,r.updated_at,
                      COALESCE(fp.name, st.name, pp.name, '') AS related_name
               FROM quant_data_requests r
               LEFT JOIN quant_factor_topics ft
                 ON r.related_type='factor_topic' AND ft.id=r.related_id
                AND ft.user_id=r.user_id AND ft.org_id=r.org_id
               LEFT JOIN detect_projects fp
                 ON fp.user_id=ft.user_id AND fp.id=ft.project_id
               LEFT JOIN strategy_topics st
                 ON r.related_type='strategy_topic' AND st.id=r.related_id
                AND st.user_id=r.user_id AND st.org_id=r.org_id
               LEFT JOIN portfolio_plans pp
                 ON r.related_type='portfolio_plan' AND pp.id=r.related_id
                AND pp.user_id=r.user_id AND pp.org_id=r.org_id
               WHERE {where} ORDER BY r.created_at DESC""", tuple(params)).fetchall()
    return [dict(r) for r in rows]


def submit_request(uid: int, org: int, payload: dict):
    fields=('title','purpose','period','frequency','fields','related_type','related_id')
    limits={'title':300,'purpose':100,'period':200,'frequency':100,'fields':2000,'related_type':50,'related_id':100}
    body={k:str(payload.get(k) or '').strip() for k in fields}
    if not body['title']:raise ValueError('请填写需要的数据')
    if any(len(body[k])>limits[k] for k in fields):raise ValueError('需求内容超出允许长度，请缩短后再提交')
    if body['related_type'] not in RELATED_TABLES:body['related_type']=body['related_id']=''
    raw=payload.get('request_id')
    try:rid=str(uuid.UUID(str(raw))) if raw else str(uuid.uuid4())
    except ValueError:raise ValueError('请求身份无效，请重新打开需求表单') from None
    with get_conn() as c:
        # Same request identity serializes across actors; never reveal another actor's row.
        if raw:c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('quant-data-request:'+rid,))
        existing=c.execute('SELECT * FROM quant_data_requests WHERE id=%s FOR UPDATE',(rid,)).fetchone() if raw else None
        if existing:
            if existing['user_id']!=uid or existing['org_id']!=org:raise ValueError('此请求身份不可用，请明确另建需求')
            if any(str(existing.get(k) or '')!=body[k] for k in fields):raise ValueError('相同请求身份的正文已改变，原需求未覆盖；如需不同内容请另建需求')
            return {k:v for k,v in dict(existing).items() if k not in ('user_id','org_id')}
        if body['related_type'] and (not body['related_id'] or not _related(uid,org,body['related_type'],body['related_id'])):
            raise ValueError('关联对象不存在或不属于当前成员')
        c.execute("""INSERT INTO quant_data_requests
               (id,user_id,org_id,title,purpose,period,frequency,fields,related_type,related_id,status,note)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'submitted','需求已保存，等待数据负责人接收；未自动转发')""",
            (rid,uid,org,*(body[k] for k in fields)))
        row=c.execute('SELECT * FROM quant_data_requests WHERE id=%s',(rid,)).fetchone()
    return {k:v for k,v in dict(row).items() if k not in ('user_id','org_id')}


def update_request(uid: int, org: int, req_id: str, payload: dict):
    status = str(payload.get("status") or "").strip()
    note = str(payload.get("note") or "").strip()
    delivered_view = str(payload.get("delivered_view") or "").strip()
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_data_requests WHERE id=%s AND org_id=%s FOR UPDATE",
            (req_id, org)).fetchone()
        if not row:
            raise KeyError(req_id)
        current = row["status"]
        if status not in TRANSITIONS:
            raise ValueError("状态只能是 in_progress / delivered / unsupported")
        if status not in TRANSITIONS[current]:
            raise ValueError(f"当前状态 {current} 不能改为 {status}")
        if status == "unsupported" and not note:
            raise ValueError("不予支持必须填写原因")
        if status == "delivered":
            if not delivered_view:
                raise ValueError("发布必须填写可用视图版本")
            if delivered_view not in _available_delivery_views():
                raise ValueError("交付视图不存在或未发布")
        c.execute(
            """UPDATE quant_data_requests
               SET status=%s,note=%s,delivered_view=%s,handled_by=%s,handled_at=NOW(),updated_at=NOW()
               WHERE id=%s AND org_id=%s""",
            (status, note[:2000], delivered_view[:100], uid, req_id, org))
        out = c.execute("SELECT * FROM quant_data_requests WHERE id=%s", (req_id,)).fetchone()
    return {k: v for k, v in dict(out).items() if k not in ("user_id", "org_id")}


__all__ = ["catalogue", "dataset", "list_requests", "submit_request", "update_request", "view_usage", "views"]
