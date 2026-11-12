# -*- coding: utf-8 -*-
"""AI 策略转写（聚宽 → SVQuant）的纯确定性校验（ADR-037 P1-4，自 ResearchEngine 迁入）。

不依赖模型、不依赖 RE 运行时：输入聚宽源码或模型草稿，输出普通 dict/list。
能力降级、合约检查、标的映射、密钥脱敏与两份 AST 校验器都在这里，
`ai/router/tasks/strategy_transcription.py` 与 `/api/ai/strategy-transcriptions` 共用。
"""
from __future__ import annotations

import ast
import re
from typing import Any

DATA_VERSION_FALLBACK = "unknown"
MAX_SOURCE_CHARS = 200_000
MAX_LLM_SOURCE_CHARS = 60_000

# 当前数据版本可注入向量化策略构造函数的字段。
VECTORIZED_FIELDS = frozenset(
    {
        "open", "high", "low", "close", "volume", "amount", "turnover",
        "current_mv", "dividend_yield_ttm", "pe_ttm", "pb_mrq",
        "pcf_operating_cash_flow_ttm", "listed_status",
        "up_and_down_status", "the_sw_industry_code",
    }
)

EVENT_FIELDS = VECTORIZED_FIELDS

SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"][^'\"]+['\"]"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{16,}\b"),
)
INJECTION_PATTERN = re.compile(
    r"(?i)(?:ignore|disregard|忽略).{0,30}(?:instruction|prompt|指令|提示词)"
    r"|system prompt|系统提示词"
)

# 允许的第三方/标准库导入；聚宽 SDK、numpy、talib 等均不在内。
ALLOWED_IMPORTS = frozenset({"pandas", "math", "statistics"})
ALLOWED_BUILTINS = frozenset(
    {
        "abs", "all", "any", "bool", "dict", "enumerate", "float", "frozenset",
        "int", "len", "list", "max", "min", "range", "round", "set", "sorted",
        "str", "sum", "tuple", "zip",
    }
)
ALLOWED_PANEL_METHODS = frozenset(
    {
        "abs", "astype", "clip", "copy", "diff", "div", "dropna", "empty", "ffill",
        "fillna", "get", "iloc", "index", "items", "max", "mean", "median", "min",
        "pct_change", "rank", "replace", "rolling", "shift", "sort_index",
        "sort_values", "std", "sum", "to_numpy", "values", "where",
    }
)
EVENT_METHODS = frozenset(
    {
        "daily", "weekly", "monthly", "history", "target_value", "target_quantity",
        "close", "quantity", "cash", "positions", "current_dt",
    }
)
GENERATABLE_DEGRADATIONS = frozenset(
    {"daily_approx", "remove_condition", "pe_ttm_proxy", "static_universe"}
)

_CHECK_ORDER = ("syntax", "contract", "security", "future_data", "fields")
_CHECK_LABELS = {
    "syntax": "语法编译",
    "contract": "策略契约",
    "security": "安全扫描",
    "future_data": "未来数据",
    "fields": "字段范围",
}


def data_version() -> str:
    """SVQuant 暂无数据版本清单；字段形状与 RE 保持一致，回退 unknown。"""
    return DATA_VERSION_FALLBACK


# ------------------------------------------------------------------ 报告结构


def make_option(
    option_id: str, label: str, risk: str, note: str, recommended: bool = False
) -> dict[str, Any]:
    return {
        "id": option_id,
        "label": label,
        "risk": risk,
        "note": note,
        "recommended": recommended,
    }


def make_issue(
    *, code: str, severity: str, impact: str, line: int, title: str,
    why: str, effect: str, options: list[dict[str, Any]], evidence: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "impact": impact,
        "line": line,
        "title": title,
        "why": why,
        "effect": effect,
        "options": options,
        "evidence": evidence,
        "confidence": "certain",
        "accepted": None,
    }


def make_check(
    check_id: str, label: str, status: str, detail: str | None = None,
    line: int | None = None,
) -> dict[str, Any]:
    return {"id": check_id, "label": label, "status": status, "detail": detail, "line": line}


def initial_checks() -> list[dict[str, Any]]:
    return [make_check(item, _CHECK_LABELS[item], "pass") for item in _CHECK_ORDER]


def skipped_checks(after: str) -> list[dict[str, Any]]:
    start = _CHECK_ORDER.index(after) + 1
    return [
        make_check(item, _CHECK_LABELS[item], "skipped", "前置检查未通过")
        for item in _CHECK_ORDER[start:]
    ]


def fail_check(
    checks: list[dict[str, Any]], check_id: str, detail: str, line: int | None = None
) -> None:
    for check in checks:
        if check["id"] == check_id:
            check["status"] = "fail"
            check["detail"] = detail
            check["line"] = line


def summary(verdict: str, issues: list[dict[str, Any]]) -> str:
    blockers = sum(1 for item in issues if item["severity"] == "blocker")
    degraded = sum(1 for item in issues if item["severity"] == "degraded")
    if verdict == "equivalent":
        return "所有调用都有直接对应，未发现需要披露的数据或时序差异。"
    if verdict == "degraded":
        return f"可以运行，但有 {degraded} 处语义差异；不是等价迁移，请逐条确认。"
    return f"存在 {blockers} 个阻断项，需要你确认降级方案后才能生成代码。"


def verdict(issues: list[dict[str, Any]]) -> str:
    if any(item["severity"] == "blocker" for item in issues):
        return "blocked"
    if any(item["severity"] == "degraded" for item in issues):
        return "degraded"
    return "equivalent"


def requires_ack(issues: list[dict[str, Any]]) -> bool:
    return any(
        item["impact"] == "high" and item["severity"] in {"blocker", "degraded"}
        for item in issues
    )


def resolve_issues(
    issues: list[dict[str, Any]], accepted: set[str]
) -> tuple[list[dict[str, Any]], list[str], bool]:
    """把已接受的可生成降级从 blocker 降为 degraded；返回 (issues, notes, 是否仍有阻断)。"""
    resolved: list[dict[str, Any]] = []
    notes: list[str] = []
    unresolved = False
    for issue in issues:
        if issue["severity"] != "blocker":
            resolved.append(issue)
            continue
        chosen = next((opt for opt in issue["options"] if opt["id"] in accepted), None)
        if chosen is not None and chosen["id"] in GENERATABLE_DEGRADATIONS:
            resolved.append({**issue, "severity": "degraded", "accepted": True})
            notes.append(f"已接受降级：{issue['title']} → {chosen['label']}（{chosen['note']}）")
        else:
            resolved.append(issue)
            unresolved = True
    return resolved, notes, unresolved


def generated_error_issue(errors: list[str]) -> dict[str, Any]:
    return make_issue(
        code="CONTRACT-GENERATED",
        severity="blocker",
        impact="high",
        line=0,
        title="生成代码未通过静态校验",
        why="模型输出没有满足目标策略契约或安全边界。",
        effect="代码不能直接提交回测，避免把不安全的或不合契约的代码当成可用草稿。",
        options=[
            make_option("retry", "重新生成", "low", "保持原输入重试", True),
            make_option("report_only", "仅导出报告", "low", "查看已识别的问题，不保存代码"),
        ],
        evidence="；".join(errors[:3]),
    )


# ------------------------------------------------------------------ inventory


class _InventoryVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.imports: list[dict[str, Any]] = []
        self.classes: list[dict[str, Any]] = []
        self.functions: list[dict[str, Any]] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = ""
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name:
            self.calls.append({"name": name, "line": node.lineno})
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append({"name": alias.name, "line": node.lineno})
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.imports.append({"name": node.module or "", "line": node.lineno})
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append({"name": node.name, "line": node.lineno})
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append({"name": node.name, "line": node.lineno})
        self.generic_visit(node)


def parse_inventory(source: str) -> dict[str, list[dict[str, Any]]]:
    """解析源码结构；语法错误抛 SyntaxError，交由调用方转成 rejected。"""
    tree = ast.parse(source)
    visitor = _InventoryVisitor()
    visitor.visit(tree)
    return {
        "calls": visitor.calls,
        "imports": visitor.imports,
        "classes": visitor.classes,
        "functions": visitor.functions,
    }


def line_of(source: str, pattern: str, flags: int = re.S) -> int:
    match = re.search(pattern, source, flags)
    if not match:
        return 0
    return source.count("\n", 0, match.start()) + 1


def detect_engine(source: str, hint: str | None) -> str:
    if hint in {"vectorized", "event"}:
        return hint
    event_markers = (
        r"\binitialize\s*\(", r"\bhandle_data\s*\(",
        r"\b(?:run_daily|run_weekly|run_monthly)\s*\(",
        r"\bbefore_trading_start\s*\(", r"\bafter_trading_end\s*\(",
        r"\border_(?:target|value|percent)\s*\(",
    )
    return "event" if any(re.search(item, source) for item in event_markers) else "vectorized"


# ------------------------------------------------------------------ capability


def capability_issues(
    source: str, inventory: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    # 代码安全：这些规则优先于业务映射，且不会被“降级”绕过。
    for pattern, code, title, why, effect, evidence in (
        (
            r"\b(?:os|sys|subprocess|socket|requests|urllib)\s*[\.\(]",
            "SECURITY-IO",
            "代码包含文件/网络/命令执行调用",
            "转写服务只接受纯计算策略；不允许访问文件、网络或系统命令。",
            "这类代码可能越权读取数据或执行任意命令，不能进入回测。",
            "安全边界：无 I/O / 网络 / 命令执行",
        ),
        (
            r"\b(?:open|eval|exec|compile|__import__|getattr|setattr|globals|locals)\s*\(",
            "SECURITY-EXEC",
            "代码包含动态执行或文件读取",
            "eval/exec/open/__import__ 等会绕过静态白名单。",
            "无法保证代码在回测环境中只做计算。",
            "安全边界：禁止动态执行与文件读取",
        ),
        (
            r"__(?!init__|name__)\w+__",
            "SECURITY-EXEC",
            "代码包含不允许的双下划线访问",
            "双下划线属性可用于绕过沙箱或访问内部对象。",
            "无法确认代码只使用策略契约内的 API。",
            "安全边界：禁止双下划线属性",
        ),
        (
            r"\b(?:random|secrets)\s*\.|\bdatetime\s*\.\s*now\s*\(|\btime\s*\.\s*time\s*\(",
            "SECURITY-NONDETERMINISM",
            "代码包含非确定性调用",
            "随机数或当前时间会让回测不可复现。",
            "同一份代码每次回测可能得到不同结果。",
            "策略规范：回测须可复现",
        ),
        (
            r"\bshift\s*\(\s*-|center\s*=\s*True",
            "LOOKAHEAD",
            "代码可能读取未来数据",
            "负周期 shift 或 rolling(center=True) 会把未来数据带入当前信号。",
            "回测结果会虚高，不能作为研究结论。",
            "向量化策略规范 §4：禁止未来数据",
        ),
    ):
        if re.search(pattern, source):
            issues.append(make_issue(
                code=code, severity="blocker", impact="high",
                line=line_of(source, pattern), title=title, why=why, effect=effect,
                options=[
                    make_option("remove_unsafe", "移除不安全调用", "low", "由你手动改写后重试"),
                    make_option("report_only", "仅导出报告", "low", "不生成可运行代码"),
                ],
                evidence=evidence,
            ))

    if INJECTION_PATTERN.search(source):
        issues.append(make_issue(
            code="SECURITY-INJECTION", severity="info", impact="low",
            line=line_of(source, INJECTION_PATTERN.pattern),
            title="代码注释可能包含指令文本",
            why="转写服务把代码当作数据；注释里的“忽略指令/系统提示词”不会被执行，也不应改变转写规则。",
            effect="不影响代码逻辑，但可能干扰模型；已按数据处理。",
            options=[
                make_option("ignore_text", "忽略注释中的指令（推荐）", "low", "继续按代码语义转写", True),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="安全边界：代码是数据，不是指令",
        ))

    if any(item.search(source) for item in SECRET_PATTERNS):
        issues.append(make_issue(
            code="SECURITY-SECRET", severity="info", impact="high",
            line=line_of(source, SECRET_PATTERNS[0].pattern),
            title="代码可能包含密钥/Token",
            why="发送给模型前会遮罩疑似密钥、Token 和 Bearer 凭据；不会写入报告或日志。",
            effect="若未遮罩，凭据可能进入模型上下文；遮罩后可能影响依赖该凭据的代码行。",
            options=[
                make_option("redacted", "发送前遮罩（推荐）", "low", "报告只提示存在敏感信息", True),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="权限边界：账号/密钥不得进入模型",
        ))

    # 分钟/Tick：数据已落盘但还没有读取接口。
    minute_pattern = (
        r"get_price\s*\([\s\S]{0,400}?frequency\s*=\s*['\"](?:1m|5m|15m|30m|60m)['\"]"
        r"|get_bars\s*\(|get_ticks\s*\(|run_daily\s*\([\s\S]{0,200}?time\s*=\s*['\"]every_bar['\"]"
    )
    if re.search(minute_pattern, source):
        issues.append(make_issue(
            code="API-UNSUPPORTED", severity="blocker", impact="high",
            line=line_of(source, minute_pattern),
            title="分钟/Tick 行情无法读取",
            why="当前只有日频研究面板；1 分钟数据虽已落盘，但 DataEngine 没有读取方法。",
            effect="盘中信号无法复现；改成日频会改变策略含义。",
            options=[
                make_option("daily_approx", "生成日频近似（高风险）", "high", "信号从分钟变日频，需你确认", True),
                make_option("wait_data", "等分钟接口接入", "low", "本期不可用"),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="09-current-data-fields §5；仅日频可读",
        ))

    # 财务/估值：财务面板未发布；估值只有部分字段。
    financial_field = re.search(r"(?:indicator|balance|cash_flow|income)\s*\.", source)
    ps_field = re.search(r"valuation\s*\.\s*ps_ttm", source)
    valuation_field = re.search(r"valuation\s*\.\s*(?:pe_ratio|pe|pb_ratio|pb)", source)
    fundamentals = re.search(r"get_fundamentals(?:_continuously)?\s*\(", source)

    if ps_field:
        issues.append(make_issue(
            code="DATA-MISSING", severity="blocker", impact="high",
            line=line_of(source, r"valuation\s*\.\s*ps_ttm"),
            title="市销率字段当前不可用",
            why="当前数据版本没有 ps_ttm 面板，不能把市现率或其他估值字段冒充市销率。",
            effect="依赖 PS 的筛选/排序无法复现。",
            options=[
                make_option("remove_condition", "移除 PS 条件", "high", "会改变选股逻辑", True),
                make_option("wait_data", "等数据接入", "low", "本期不可用"),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="09-current-data-fields §7",
        ))
    elif financial_field or (fundamentals and not valuation_field):
        issues.append(make_issue(
            code="DATA-MISSING", severity="blocker", impact="high",
            line=line_of(source, r"(?:indicator|balance|cash_flow|income)\s*\.") or line_of(source, r"get_fundamentals(?:_continuously)?\s*\("),
            title="财务字段当前不可用",
            why="财务面板尚未发布（DATA-002 待授权），策略运行时没有 ROE、Piotroski 等会计字段。",
            effect="依赖财务条件的选股逻辑无法计算；用估值代理不是同一个因子。",
            options=[
                make_option("remove_condition", "移除财务条件", "high", "会改变选股逻辑，需你确认", True),
                make_option("wait_data", "等财务数据接入", "low", "本期不可用"),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="FEAT-010 数据清单 DATA-002；09-current-data-fields §7",
        ))
    elif valuation_field:
        issues.append(make_issue(
            code="SEMANTIC-DATA", severity="degraded", impact="high",
            line=line_of(source, r"valuation\s*\.\s*(?:pe_ratio|pe|pb_ratio|pb)"),
            title="估值口径与聚宽不同",
            why="聚宽 pe_ratio/pb_ratio 与 SVQuant 的 pe_ttm/pb_mrq 口径不同；估值/行业面板当前只有 406 行覆盖。",
            effect="静态 PE 与 TTM PE 的排序可能不同，长周期回测还会遇到覆盖不足。",
            options=[
                make_option("pe_ttm_proxy", "映射到 pe_ttm/pb_mrq（推荐）", "medium", "口径不同，报告标注", True),
                make_option("remove_condition", "移除估值条件", "high", "会改变选股逻辑"),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="09-current-data-fields §3、§7",
        ))

    # 股票池：回测起点静态解析。
    if re.search(r"get_index_stocks\s*\(", source):
        issues.append(make_issue(
            code="SEMANTIC-UNIVERSE", severity="degraded", impact="high",
            line=line_of(source, r"get_index_stocks\s*\("),
            title="指数成分只能取回测起点快照",
            why="SVQuant 的股票池在回测数据起点解析，之后不随指数调样动态切换；聚宽按调仓日取当时成分。",
            effect="忽略历史调样，早期样本存在幸存者偏差；换手与收益可能偏离。",
            options=[
                make_option("static_universe", "接受静态快照（推荐）", "high", "最快，报告注明偏差", True),
                make_option("custom_snapshot", "提供点时成分文件", "medium", "需要按调仓日准备"),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="事件策略规范 §3；当前数据只有 CSI300/CSI500 成分快照",
        ))

    if re.search(r"order_target_percent\s*\(", source):
        issues.append(make_issue(
            code="SEMANTIC-ORDER", severity="degraded", impact="high",
            line=line_of(source, r"order_target_percent\s*\("),
            title="目标百分比只能近似",
            why="事件组合只暴露 cash/positions/quantity，没有 total_value；无法精确按总资产计算百分比。",
            effect="仓位会随前收盘估值漂移；满仓或空仓时偏差更明显。",
            options=[
                make_option("equity_proxy", "用前收盘近似总资产（推荐）", "medium", "改动最小，报告标注", True),
                make_option("fixed_value", "改成固定金额", "medium", "仓位不再随总资产变化"),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="事件策略规范 §3；组合接口仅 cash/positions/quantity",
        ))

    if re.search(r"order_(?:value|target)\s*\(", source):
        issues.append(make_issue(
            code="SEMANTIC-ORDER", severity="degraded", impact="medium",
            line=line_of(source, r"order_(?:value|target)\s*\("),
            title="增量订单需要换算成目标仓位",
            why="聚宽 order/order_value 是增量下单；SVQuant 只接受目标数量、目标金额或清仓。",
            effect="换算依赖当前持仓与前收盘估值，成交价不同会造成轻微偏差。",
            options=[
                make_option("target_order", "换算为目标仓位（推荐）", "medium", "按当前持仓 + 增量计算", True),
                make_option("fixed_value", "改成固定金额", "medium", "不再依赖当前持仓"),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="事件策略规范 §4",
        ))

    if re.search(r"attribute_history\s*\(|get_price\s*\(", source):
        issues.append(make_issue(
            code="SEMANTIC-FQ", severity="degraded", impact="medium",
            line=line_of(source, r"attribute_history\s*\(|get_price\s*\("),
            title="复权口径与聚宽默认不同",
            why="SVQuant 研究/回测价格固定为后复权；聚宽默认前复权，且当前没有 adj_factor 可逐调用切换。",
            effect="除权除息日附近的历史收盘序列不同，均线/RSI 等价格信号可能略有偏离。",
            options=[
                make_option("accept_hfq", "接受后复权（推荐）", "medium", "改动最小，报告标注", True),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="09-current-data-fields §7–§8",
        ))

    if re.search(r"get_current_data\s*\(|get_extras\s*\(", source):
        issues.append(make_issue(
            code="SEMANTIC-SUSPEND", severity="degraded", impact="high",
            line=line_of(source, r"get_current_data\s*\(|get_extras\s*\("),
            title="ST/停牌/涨跌停没有逐标的实时对象",
            why="当前没有 is_st/is_suspended/limit_up 布尔字段；只有 listed_status/up_and_down_status 原文，撮合层会拒单。",
            effect="策略内过滤无法完全复刻；只能依赖请求过滤开关与撮合拒单。",
            options=[
                make_option("engine_filters", "用过滤开关 + 撮合拒单（推荐）", "medium", "报告标注差异", True),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="09-current-data-fields §7；撮合层拒单规则",
        ))

    if re.search(r"get_industry\s*\(", source):
        issues.append(make_issue(
            code="SEMANTIC-INDUSTRY", severity="degraded", impact="high",
            line=line_of(source, r"get_industry\s*\("),
            title="行业分类非全历史点时数据",
            why="当前只有 the_sw_industry_code，覆盖 406 行，且没有行业名称字段。",
            effect="行业中性化可能引入时点偏差；历史行业缺失时结果不可比。",
            options=[
                make_option("static_industry", "静态行业 + 覆盖说明（推荐）", "high", "报告标注覆盖限制", True),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="09-current-data-fields §3.1、§6",
        ))

    if re.search(r"cancel_order\s*\(|get_open_orders\s*\(|get_orders\s*\(", source):
        issues.append(make_issue(
            code="API-UNSUPPORTED", severity="degraded", impact="high",
            line=line_of(source, r"cancel_order\s*\(|get_open_orders\s*\(|get_orders\s*\("),
            title="订单生命周期接口不可用",
            why="SVQuant 没有 get_open_orders/get_orders/cancel_order，只能提交目标仓位。",
            effect="挂单管理、撤单和部分成交逻辑无法复现。",
            options=[
                make_option("target_order", "改为一次性目标仓位（推荐）", "medium", "不做挂单管理", True),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="事件策略规范 §6",
        ))

    if re.search(r"\blog\s*\.|\brecord\s*\(", source):
        issues.append(make_issue(
            code="API-UNSUPPORTED", severity="info", impact="low",
            line=line_of(source, r"\blog\s*\.|\brecord\s*\("),
            title="策略日志/图表记录不可用",
            why="事件策略没有 log/record API；可用回测执行时间线查看订单与成交。",
            effect="过程可观测性下降，但不影响策略计算。",
            options=[
                make_option("drop_log", "移除日志/记录（推荐）", "low", "转成注释或删除", True),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="事件策略规范 §3",
        ))

    issues.extend(contract_issues(source, inventory))
    issues.extend(instrument_issues(source, inventory))
    return dedupe_issues(issues)


def dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, int]] = set()
    result: list[dict[str, Any]] = []
    for issue in issues:
        key = (issue["code"], issue["line"])
        if key in seen:
            continue
        seen.add(key)
        result.append(issue)
    result.sort(
        key=lambda item: (
            0 if item["severity"] == "blocker" else 1 if item["severity"] == "degraded" else 2,
            item["line"],
        )
    )
    return result


def contract_issues(
    source: str, inventory: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    imports = {item["name"].split(".")[0] for item in inventory["imports"]}
    forbidden = imports - ALLOWED_IMPORTS
    if "jqdata" in forbidden or "jqfactor" in forbidden:
        line = line_of(source, r"(?:from|import)\s+(?:jqdata|jqfactor)")
        issues.append(make_issue(
            code="CONTRACT-IMPORT", severity="blocker", impact="high", line=line,
            title="代码依赖聚宽 SDK",
            why="转写服务不引入 jqdata/jqfactor 运行时，也不会连接聚宽账号。",
            effect="代码无法在本平台执行，且聚宽数据/接口不能直接复用。",
            options=[
                make_option("rewrite_import", "移除聚宽 SDK 并改写（推荐）", "medium", "由模型按平台字段改写", True),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="事件策略规范 §6：不提供 jqdata 兼容接口",
        ))
    other = sorted(forbidden - {"jqdata", "jqfactor"})
    if other:
        issues.append(make_issue(
            code="CONTRACT-IMPORT", severity="blocker", impact="medium",
            line=line_of(source, r"(?:from|import)\s+\w+"),
            title="代码包含未允许的导入",
            why=f"只允许聚合计算所需的 {', '.join(sorted(ALLOWED_IMPORTS))}；当前包含：{', '.join(other)}。",
            effect="外部库可能存在 I/O、网络或不可控依赖，无法进入受控回测。",
            options=[
                make_option("rewrite_import", "改写为允许的库（推荐）", "medium", "用 pandas/math/statistics 重写", True),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="AI 策略生成契约：仅 pandas 与纯计算库",
        ))
    if len(inventory["classes"]) > 1:
        issues.append(make_issue(
            code="CONTRACT-MULTI-CLASS", severity="blocker", impact="medium",
            line=inventory["classes"][1]["line"],
            title="代码包含多个策略类",
            why="目标契约要求单文件、唯一策略类；多个类会让入口不明确。",
            effect="引擎无法确定入口，回测可能加载错误的类。",
            options=[
                make_option("split_strategy", "拆分为多个策略文件（推荐）", "medium", "每次只转一个策略", True),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="向量化/事件策略契约：唯一策略类",
        ))
    return issues


def instrument_issues(
    source: str, inventory: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if re.search(r"get_dominant_contract\s*\(|\bfutures?\b|\.(?:IC|IF|IH|IM)\d", source, re.I):
        issues.append(make_issue(
            code="OUT-OF-SCOPE-INSTRUMENT", severity="blocker", impact="high",
            line=line_of(source, r"get_dominant_contract\s*\(|\bfutures?\b|\.(?:IC|IF|IH|IM)\d"),
            title="期货标的不在本期范围",
            why="当前策略运行时只支持 A 股现金多头，不支持期货合约、保证金和换月。",
            effect="无法回测或复现期货策略。",
            options=[
                make_option("remove_instrument", "移除期货标的", "medium", "改用股票策略", True),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="事件策略规范 §6",
        ))
    if re.search(r"['\"](?:51|15|16|18)\d{4}\.(?:XSHG|XSHE|SH|SZ)['\"]", source):
        issues.append(make_issue(
            code="OUT-OF-SCOPE-INSTRUMENT", severity="blocker", impact="high",
            line=line_of(source, r"['\"](?:51|15|16|18)\d{4}\.(?:XSHG|XSHE|SH|SZ)['\"]"),
            title="ETF/LOF 不在本期范围",
            why="当前数据与交易规则面向 A 股股票，不支持 ETF T+0 与基金申赎。",
            effect="ETF 策略的成交与费用规则无法复现。",
            options=[
                make_option("remove_instrument", "换成股票标的", "medium", "会改变策略", True),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="事件策略规范 §6",
        ))
    if re.search(r"side\s*=\s*['\"]short['\"]|融资|融券|做空", source, re.I):
        issues.append(make_issue(
            code="OUT-OF-SCOPE-INSTRUMENT", severity="blocker", impact="high",
            line=line_of(source, r"side\s*=\s*['\"]short['\"]|融资|融券|做空"),
            title="做空/两融不在本期范围",
            why="当前只支持 A 股现金多头，没有融资融券和空头持仓。",
            effect="无法复现做空收益与保证金风险。",
            options=[
                make_option("remove_short", "改为纯多头", "high", "会改变策略含义", True),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="事件策略规范 §6",
        ))
    if re.search(r"send_message\s*\(|send_email\s*\(", source):
        issues.append(make_issue(
            code="OUT-OF-SCOPE-LIVE", severity="blocker", impact="high",
            line=line_of(source, r"send_message\s*\(|send_email\s*\("),
            title="策略不能对外发送消息",
            why="转写服务不提供消息/邮件副作用，也不代表用户对外通信。",
            effect="存在越权外发风险，代码不能执行。",
            options=[
                make_option("remove_side_effect", "移除外发调用（推荐）", "low", "改为策略注释", True),
                make_option("report_only", "仅导出报告", "low", "不生成代码"),
            ],
            evidence="权限边界：禁止外部副作用",
        ))
    return issues


def transcription_mappings(
    source: str, inventory: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    call_lines = {item["name"]: item["line"] for item in inventory["calls"]}
    for jq, svq, status, note in (
        ("get_index_stocks", "universe=CSI300/CSI500（请求配置）", "degraded", "回测起点静态解析"),
        ("get_price", "context.data.history / 向量化面板", "degraded", "固定后复权"),
        ("attribute_history", "context.data.history", "degraded", "固定后复权"),
        ("run_daily", "context.schedule.daily", "equivalent", "盘前回调"),
        ("run_weekly", "context.schedule.weekly", "equivalent", "按交易日调度"),
        ("run_monthly", "context.schedule.monthly", "equivalent", "每月第 N 个交易日"),
        ("order_target_value", "context.orders.target_value", "equivalent", "目标金额"),
        ("order_target", "context.orders.target_quantity", "equivalent", "目标数量"),
        ("order_target_percent", "target_value(equity * pct)", "degraded", "总资产近似"),
        ("order_value", "target_value(当前市值 + value)", "degraded", "增量换算"),
        ("order", "target_quantity(当前数量 + amount)", "degraded", "增量换算"),
        ("set_benchmark", "请求 benchmark", "config", "仅支持可用指数"),
        ("set_order_cost", "请求佣金/印花税/最低佣金", "config", "固定费率"),
        ("set_slippage", "请求 slippage_rate", "config", "固定比例"),
        ("get_current_data", "过滤开关 + 撮合拒单", "degraded", "无逐标的实时对象"),
        ("get_industry", "the_sw_industry_code", "degraded", "覆盖 406 行"),
        ("get_trade_days", "schedule + current_dt", "degraded", "无策略内日历 API"),
    ):
        if jq in call_lines:
            mappings.append({
                "jq": jq, "svq": svq, "status": status,
                "line": call_lines[jq], "note": note,
            })
    if "get_fundamentals" in call_lines:
        pe_only = (
            re.search(r"valuation\s*\.\s*(?:pe_ratio|pe|pb_ratio|pb)", source)
            and not re.search(r"(?:indicator|balance|cash_flow|income)\s*\.", source)
            and not re.search(r"valuation\s*\.\s*ps_ttm", source)
        )
        mappings.append({
            "jq": "get_fundamentals",
            "svq": "pe_ttm/pb_mrq 面板" if pe_only else "无对应财务接口",
            "status": "degraded" if pe_only else "blocked",
            "line": call_lines["get_fundamentals"],
            "note": "口径不同" if pe_only else "财务面板未发布",
        })
    if re.search(r"\bg\.", source):
        mappings.append({
            "jq": "g.xxx", "svq": "context.state.xxx", "status": "equivalent",
            "line": line_of(source, r"\bg\."), "note": "策略私有状态",
        })
    return mappings


# ------------------------------------------------------------------ prompt


def redact_secrets(source: str) -> str:
    """在发送给模型前遮罩疑似凭据；报告只提示存在敏感信息。"""
    def replace_assignment(match: re.Match[str]) -> str:
        text = match.group(0)
        for separator in ("=", ":"):
            if separator in text:
                prefix = text.split(separator, 1)[0]
                return f"{prefix}{separator}'***REDACTED***'"
        return "***REDACTED***"

    redacted = source
    for index, pattern in enumerate(SECRET_PATTERNS):
        redacted = pattern.sub(replace_assignment if index == 0 else "***REDACTED***", redacted)
    return redacted


# -------------------------------------------------------------- validation


def security_errors(source: str) -> list[str]:
    errors: list[str] = []
    patterns = (
        (r"\b(?:os|sys|subprocess|socket|requests|urllib)\s*[\.\(]", "禁止文件/网络/命令执行调用"),
        (r"\b(?:open|eval|exec|compile|__import__|getattr|setattr|globals|locals)\s*\(", "禁止动态执行或文件读取"),
        (r"__(?!init__|name__)\w+__", "禁止双下划线属性访问"),
        (r"\b(?:random|secrets)\s*\.|\bdatetime\s*\.\s*now\s*\(|\btime\s*\.\s*time\s*\(", "禁止非确定性调用"),
    )
    for pattern, message in patterns:
        if re.search(pattern, source):
            errors.append(message)
    return errors


def future_data_errors(source: str) -> list[str]:
    errors: list[str] = []
    if re.search(r"\bshift\s*\(\s*-", source):
        errors.append("禁止负周期 shift（未来数据）")
    if re.search(r"center\s*=\s*True", source):
        errors.append("禁止 rolling(center=True)（未来数据）")
    return errors


def field_errors(strategy: dict[str, Any], tree: ast.Module, target_engine: str) -> list[str]:
    allowed = VECTORIZED_FIELDS if target_engine == "vectorized" else EVENT_FIELDS
    unknown = sorted(set(strategy.get("used_fields") or []) - allowed)
    if unknown:
        return [f"used_fields 包含未登记字段：{', '.join(unknown)}"]
    if target_engine == "vectorized":
        constructors = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        if constructors:
            init = next(
                (
                    item
                    for item in constructors[0].body
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__"
                ),
                None,
            )
            if init is not None:
                args = [arg.arg for arg in init.args.args][1:]
                bad = sorted(set(args) - allowed)
                if bad:
                    return [f"__init__ 包含不可注入字段：{', '.join(bad)}"]
    return []


def vectorized_contract_errors(strategy: dict[str, Any], tree: ast.Module) -> list[str]:
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    if len(classes) != 1:
        return ["向量化策略必须只包含一个策略类"]
    if len(tree.body) not in {1, 2}:
        return ["向量化策略只允许 pandas 导入和一个策略类定义"]
    cls = classes[0]
    if cls.name != strategy.get("strategy_name"):
        return ["策略类名必须与 strategy_name 一致"]
    methods = [node.name for node in cls.body if isinstance(node, ast.FunctionDef)]
    if methods != ["__init__", "generate_signals"]:
        return ["向量化策略必须且只能定义 __init__ 与 generate_signals"]
    for method in cls.body:
        if not isinstance(method, ast.FunctionDef):
            continue
        if method.decorator_list:
            return ["策略方法不允许装饰器"]
        args = [arg.arg for arg in method.args.args]
        if method.name == "__init__":
            if len(args) < 2 or args[0] != "self":
                return ["__init__ 必须接收 self + 至少一个面板字段"]
        elif args != ["self"]:
            return ["generate_signals 不能带额外参数"]
    if not _has_import(tree, "pandas"):
        return ["向量化策略必须 import pandas as pd"]
    validator = _VectorizedAstValidator(VECTORIZED_FIELDS)
    validator.visit(tree)
    return validator.errors


def event_contract_errors(strategy: dict[str, Any], tree: ast.Module) -> list[str]:
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    if len(classes) != 1:
        return ["事件策略必须只包含一个策略类"]
    cls = classes[0]
    if cls.name != strategy.get("strategy_name"):
        return ["策略类名必须与 strategy_name 一致"]
    methods = [node.name for node in cls.body if isinstance(node, ast.FunctionDef)]
    if "initialize" not in methods:
        return ["事件策略必须定义 initialize(self, context)"]
    init = next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == "initialize"
    )
    args = [arg.arg for arg in init.args.args]
    if args != ["self", "context"]:
        return ["initialize 签名必须是 (self, context)"]
    if any(item.decorator_list for item in cls.body if isinstance(item, ast.FunctionDef)):
        return ["策略方法不允许装饰器"]
    validator = _EventAstValidator()
    validator.visit(tree)
    return validator.errors


def _has_import(tree: ast.Module, name: str) -> bool:
    for node in tree.body:
        if isinstance(node, ast.Import):
            if any(alias.name == name for alias in node.names):
                return True
        if isinstance(node, ast.ImportFrom) and node.module == name:
            return True
    return False


class _VectorizedAstValidator(ast.NodeVisitor):
    _ALLOWED_NODES = {
        ast.Module, ast.Import, ast.alias, ast.ClassDef, ast.FunctionDef, ast.arguments,
        ast.arg, ast.Return, ast.Assign, ast.Name, ast.Load, ast.Store, ast.Attribute,
        ast.Call, ast.Constant, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult,
        ast.Div, ast.Pow, ast.USub, ast.Compare, ast.Eq, ast.NotEq, ast.Gt, ast.GtE,
        ast.Lt, ast.LtE, ast.keyword, ast.Subscript, ast.Mod, ast.Slice, ast.List,
        ast.Tuple, ast.BitAnd, ast.BitOr, ast.BoolOp, ast.And, ast.Or, ast.IfExp,
    }

    def __init__(self, fields: frozenset[str]) -> None:
        self.fields = fields
        self.errors: list[str] = []

    def generic_visit(self, node: ast.AST) -> None:
        if type(node) not in self._ALLOWED_NODES:
            self.errors.append(f"不允许的代码结构：{type(node).__name__}")
            return
        super().generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        if len(node.names) != 1 or node.names[0].name != "pandas" or node.names[0].asname != "pd":
            self.errors.append("只允许 import pandas as pd")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        methods = [item.name for item in node.body if isinstance(item, ast.FunctionDef)]
        if methods != ["__init__", "generate_signals"]:
            self.errors.append("策略类必须且只能定义 __init__ 与 generate_signals")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        args = [arg.arg for arg in node.args.args]
        if node.name == "__init__":
            if len(args) < 2 or args[0] != "self" or any(item not in self.fields for item in args[1:]):
                self.errors.append("__init__ 的参数必须是 self + 可用面板字段")
        elif node.name == "generate_signals":
            if args != ["self"]:
                self.errors.append("generate_signals 不能带额外参数")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__"):
            self.errors.append("不允许访问双下划线属性")
        if isinstance(node.value, ast.Name) and node.value.id == "self" and node.attr not in self.fields:
            self.errors.append(f"不允许的 self 属性：{node.attr}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "pd":
                if node.func.attr in {"DataFrame", "Series"}:
                    self.generic_visit(node)
                    return
            if node.func.attr not in ALLOWED_PANEL_METHODS:
                self.errors.append(f"不允许调用：{node.func.attr}")
        elif isinstance(node.func, ast.Name):
            if node.func.id not in ALLOWED_BUILTINS:
                self.errors.append(f"不允许调用：{node.func.id}")
        else:
            self.errors.append("不允许的调用形式")
        self.generic_visit(node)


class _EventAstValidator(ast.NodeVisitor):
    _ALLOWED_NODES = {
        ast.Module, ast.Import, ast.ImportFrom, ast.alias, ast.ClassDef, ast.FunctionDef,
        ast.arguments, ast.arg, ast.Return, ast.Assign, ast.AugAssign, ast.Name,
        ast.Load, ast.Store, ast.Attribute, ast.Call, ast.Constant, ast.BinOp,
        ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub,
        ast.Compare, ast.Eq, ast.NotEq, ast.Gt, ast.GtE, ast.Lt, ast.LtE,
        ast.keyword, ast.Subscript, ast.Mod, ast.Slice, ast.List, ast.Tuple,
        ast.Dict, ast.Set, ast.BitAnd, ast.BitOr, ast.BoolOp, ast.And, ast.Or,
        ast.Not, ast.If, ast.For, ast.comprehension, ast.GeneratorExp, ast.IfExp,
        ast.Expr, ast.Pass, ast.Break, ast.Continue,
    }

    def __init__(self) -> None:
        self.errors: list[str] = []

    def generic_visit(self, node: ast.AST) -> None:
        if type(node) not in self._ALLOWED_NODES:
            self.errors.append(f"不允许的代码结构：{type(node).__name__}")
            return
        super().generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name not in ALLOWED_IMPORTS:
                self.errors.append(f"不允许导入：{alias.name}")
            if alias.name in {"pandas"} and alias.asname not in {None, "pd"}:
                self.errors.append("pandas 只允许使用别名 pd")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.errors.append("事件策略只允许 import，不允许 from ... import")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__"):
            self.errors.append("不允许访问双下划线属性")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if attr not in EVENT_METHODS and attr not in ALLOWED_PANEL_METHODS:
                self.errors.append(f"不允许调用：{attr}")
        elif isinstance(node.func, ast.Name):
            if node.func.id not in ALLOWED_BUILTINS:
                self.errors.append(f"不允许调用：{node.func.id}")
        else:
            self.errors.append("不允许的调用形式")
        self.generic_visit(node)


def validate_transcribed_strategy(
    strategy: dict[str, Any], target_engine: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """对模型草稿做语法/契约/安全/未来数据/字段检查；返回 (checks, errors)。"""
    checks = initial_checks()
    errors: list[str] = []

    name = str(strategy.get("strategy_name") or "")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        errors.append("strategy_name 必须是合法的 Python 类名")
        fail_check(checks, "contract", errors[-1])

    code = str(strategy.get("strategy_code") or "")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        errors.append(f"策略代码语法错误：第 {exc.lineno} 行，{exc.msg}")
        fail_check(checks, "syntax", errors[-1], exc.lineno)
        return checks, errors

    security = security_errors(code)
    if security:
        errors.extend(security)
        fail_check(checks, "security", security[0])

    future = future_data_errors(code)
    if future:
        errors.extend(future)
        fail_check(checks, "future_data", future[0])

    fields = field_errors(strategy, tree, target_engine)
    if fields:
        errors.extend(fields)
        fail_check(checks, "fields", fields[0])

    contract = (
        vectorized_contract_errors(strategy, tree)
        if target_engine == "vectorized"
        else event_contract_errors(strategy, tree)
    )
    if contract:
        errors.extend(contract)
        fail_check(checks, "contract", contract[0])

    try:
        compile(code, "<transcribed_strategy>", "exec")
    except SyntaxError as exc:
        errors.append(f"策略代码无法编译：{exc.msg}")
        fail_check(checks, "syntax", errors[-1], exc.lineno)

    return checks, errors


__all__ = [
    "ALLOWED_BUILTINS",
    "ALLOWED_IMPORTS",
    "ALLOWED_PANEL_METHODS",
    "DATA_VERSION_FALLBACK",
    "EVENT_FIELDS",
    "EVENT_METHODS",
    "GENERATABLE_DEGRADATIONS",
    "INJECTION_PATTERN",
    "MAX_LLM_SOURCE_CHARS",
    "MAX_SOURCE_CHARS",
    "SECRET_PATTERNS",
    "VECTORIZED_FIELDS",
    "capability_issues",
    "contract_issues",
    "data_version",
    "dedupe_issues",
    "detect_engine",
    "event_contract_errors",
    "fail_check",
    "field_errors",
    "future_data_errors",
    "generated_error_issue",
    "initial_checks",
    "instrument_issues",
    "line_of",
    "make_check",
    "make_issue",
    "make_option",
    "parse_inventory",
    "redact_secrets",
    "requires_ack",
    "resolve_issues",
    "security_errors",
    "skipped_checks",
    "summary",
    "transcription_mappings",
    "validate_transcribed_strategy",
    "vectorized_contract_errors",
    "verdict",
]
