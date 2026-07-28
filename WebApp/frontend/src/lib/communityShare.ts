import type { CommunitySection } from "@/lib/communityApi";

/** 发帖助手 / Critic：平台结果引用（有则背书数字） */
export type PlatformMetricsRef = {
  source: "factor_panel" | "factor_detect" | "strategy_report" | string;
  label: string;
  factor_name?: string;
  universe?: string;
  period?: string;
  /** 面板查库用码，如 CSI300 / 3y */
  universe_code?: string;
  period_code?: string;
  library?: string;
  filter_limit_up?: boolean;
  metrics_display: Record<string, string>;
  metrics?: Record<string, number | null | undefined>;
};

/** 发帖页 location.state 预填（报告分享 / 其它入口） */
export type CommunityShareDraft = {
  shareDraft?: true;
  section?: CommunitySection;
  title?: string;
  /** TipTap 所见即所得：传 HTML，避免编辑器里露出 ** markdown */
  body?: string;
  code_snippet?: string;
  /** 取消 / 左上角返回：回到分享来源页（检测报告 / 策略报告） */
  returnTo?: string;
  returnLabel?: string;
  /** 面板/报告带来的真源指标；AI 助手只认这个 */
  platform_ref?: PlatformMetricsRef;
};

function pct(x?: number | null) {
  if (x == null || Number.isNaN(x)) return null;
  return `${(x * 100).toFixed(2)}%`;
}

function num(x?: number | null) {
  if (x == null || Number.isNaN(x)) return null;
  return x.toFixed(2);
}

function esc(s: string) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function metricListHtml(
  pairs: Array<[string, string | null | undefined]>,
): string {
  const items = pairs
    .filter(([, v]) => v != null && String(v).trim() !== "")
    .map(([k, v]) => `<li><strong>${esc(k)}</strong>：${esc(String(v))}</li>`);
  if (!items.length) return "<ul><li>（暂无指标摘要）</li></ul>";
  return `<ul>${items.join("")}</ul>`;
}

export function buildFactorDetectShareDraft(input: {
  /** 展示名：用户起的检测项目名，如 max */
  name: string;
  rangeLabel?: string;
  universeLabel?: string;
  benchmarkLabel?: string;
  metrics?: {
    sharpe?: number | null;
    annual_return?: number | null;
    max_drawdown?: number | null;
    rank_ic?: number | null;
    ic?: number | null;
    win_rate?: number | null;
  } | null;
  excessReturn?: number | null;
  factorCode?: string | null;
  /** RE 内置库（单因子无 factor_code 时用于生成可克隆存根） */
  libraryName?: string | string[] | null;
  factorName?: string | null;
  returnTo?: string;
  returnLabel?: string;
}): CommunityShareDraft {
  const titleBase = (input.name || "因子检测").trim();
  const title = `【因子检测】${titleBase}`.slice(0, 120);
  const m = input.metrics;
  const meta: string[] = [
    `<p><strong>因子</strong>：<code>${esc(titleBase)}</code></p>`,
  ];
  if (input.rangeLabel) {
    meta.push(`<p><strong>区间</strong>：${esc(input.rangeLabel)}</p>`);
  }
  if (input.universeLabel) {
    meta.push(`<p><strong>股票池</strong>：${esc(input.universeLabel)}</p>`);
  }
  if (input.benchmarkLabel) {
    meta.push(`<p><strong>基准</strong>：${esc(input.benchmarkLabel)}</p>`);
  }
  const body = [
    "<p>来自因子检测报告自动摘要。</p>",
    ...meta,
    "<p><strong>指标摘要</strong></p>",
    metricListHtml([
      ["年化", pct(m?.annual_return)],
      ["夏普", num(m?.sharpe)],
      ["最大回撤", pct(m?.max_drawdown)],
      ["Rank IC", num(m?.rank_ic ?? m?.ic)],
      ["胜率", pct(m?.win_rate)],
      ["超额", pct(input.excessReturn)],
    ]),
    "<blockquote><p>免责声明：内容不构成投资建议。</p></blockquote>",
  ].join("");

  const code = resolveShareFactorCode(input);

  const metrics_display: Record<string, string> = {};
  const put = (k: string, v: string | null | undefined) => {
    if (v != null && String(v).trim()) metrics_display[k] = String(v);
  };
  put("年化", pct(m?.annual_return) || undefined);
  put("夏普", num(m?.sharpe) || undefined);
  put("最大回撤", pct(m?.max_drawdown) || undefined);
  put("Rank IC", num(m?.rank_ic ?? m?.ic) || undefined);
  put("胜率", pct(m?.win_rate) || undefined);
  put("超额", pct(input.excessReturn) || undefined);

  return {
    shareDraft: true,
    section: "factor",
    title,
    body,
    code_snippet: code || undefined,
    returnTo: input.returnTo,
    returnLabel: input.returnLabel,
    platform_ref: Object.keys(metrics_display).length
      ? {
          source: "factor_detect",
          label: `因子检测 · ${titleBase}${input.universeLabel ? ` · ${input.universeLabel}` : ""}${input.rangeLabel ? ` · ${input.rangeLabel}` : ""}`,
          factor_name: titleBase,
          universe: input.universeLabel,
          period: input.rangeLabel,
          metrics_display,
          metrics: {
            annual_return: m?.annual_return ?? undefined,
            sharpe: m?.sharpe ?? undefined,
            max_drawdown: m?.max_drawdown ?? undefined,
            rank_ic: m?.rank_ic ?? m?.ic ?? undefined,
            win_rate: m?.win_rate ?? undefined,
            excess_return: input.excessReturn ?? undefined,
          },
        }
      : undefined,
  };
}

/** 纯 library_name 检测无 factor_code 时，生成带正确 def 名的存根供社区克隆 */
export function buildBuiltinFactorShareStub(
  factorName: string,
  libraryName: string | string[],
): string {
  const lib = Array.isArray(libraryName) ? libraryName.join(", ") : libraryName;
  const safe =
    /^[A-Za-z_][A-Za-z0-9_]*$/.test(factorName) ? factorName : "shared_factor";
  return [
    `def ${safe}(self):`,
    `    """公用库因子 · ${lib}`,
    `    克隆到因子检测：自动选用同名公用因子（RE library_name）。`,
    `    克隆到策略研究：经典/聚宽拉本地实现；qlib_* 按命名展开公式。`,
    `    """`,
    `    pass`,
  ].join("\n");
}

function resolveShareFactorCode(input: {
  factorCode?: string | null;
  libraryName?: string | string[] | null;
  factorName?: string | null;
}): string {
  const code = (input.factorCode || "").trim();
  if (code) return code;
  const fname = (input.factorName || "").trim();
  const lib = input.libraryName;
  if (fname && lib) return buildBuiltinFactorShareStub(fname, lib);
  return "";
}

export function buildStrategyShareDraft(input: {
  name: string;
  rangeLabel?: string;
  universeLabel?: string;
  benchmarkLabel?: string;
  metrics?: {
    sharpe?: number | null;
    annual_return?: number | null;
    max_drawdown?: number | null;
    win_rate?: number | null;
    total_return?: number | null;
    cumulative_return?: number | null;
  } | null;
  excessReturn?: number | null;
  strategyCode?: string | null;
  returnTo?: string;
  returnLabel?: string;
}): CommunityShareDraft {
  const titleBase = (input.name || "策略回测").trim();
  const title = `【策略回测】${titleBase}`.slice(0, 120);
  const m = input.metrics;
  const meta: string[] = [];
  if (input.rangeLabel) {
    meta.push(`<p><strong>区间</strong>：${esc(input.rangeLabel)}</p>`);
  }
  if (input.universeLabel) {
    meta.push(`<p><strong>股票池</strong>：${esc(input.universeLabel)}</p>`);
  }
  if (input.benchmarkLabel) {
    meta.push(`<p><strong>基准</strong>：${esc(input.benchmarkLabel)}</p>`);
  }
  const body = [
    "<p>来自策略回测报告自动摘要。</p>",
    ...meta,
    "<p><strong>指标摘要</strong></p>",
    metricListHtml([
      ["年化", pct(m?.annual_return)],
      ["夏普", num(m?.sharpe)],
      ["最大回撤", pct(m?.max_drawdown)],
      ["胜率", pct(m?.win_rate)],
      ["累计收益", pct(m?.total_return ?? m?.cumulative_return)],
      ["超额", pct(input.excessReturn)],
    ]),
    "<blockquote><p>免责声明：内容不构成投资建议。</p></blockquote>",
  ].join("");

  return {
    shareDraft: true,
    section: "strategy",
    title,
    body,
    code_snippet: (input.strategyCode || "").trim() || undefined,
    returnTo: input.returnTo,
    returnLabel: input.returnLabel,
    platform_ref: (() => {
      const metrics_display: Record<string, string> = {};
      const put = (k: string, v: string | null | undefined) => {
        if (v != null && String(v).trim()) metrics_display[k] = String(v);
      };
      put("年化", pct(m?.annual_return) || undefined);
      put("夏普", num(m?.sharpe) || undefined);
      put("最大回撤", pct(m?.max_drawdown) || undefined);
      put("胜率", pct(m?.win_rate) || undefined);
      put("累计收益", pct(m?.total_return ?? m?.cumulative_return) || undefined);
      put("超额", pct(input.excessReturn) || undefined);
      if (!Object.keys(metrics_display).length) return undefined;
      return {
        source: "strategy_report" as const,
        label: `策略回测 · ${titleBase}${input.universeLabel ? ` · ${input.universeLabel}` : ""}${input.rangeLabel ? ` · ${input.rangeLabel}` : ""}`,
        universe: input.universeLabel,
        period: input.rangeLabel,
        metrics_display,
        metrics: {
          annual_return: m?.annual_return ?? undefined,
          sharpe: m?.sharpe ?? undefined,
          max_drawdown: m?.max_drawdown ?? undefined,
          win_rate: m?.win_rate ?? undefined,
          total_return: m?.total_return ?? m?.cumulative_return ?? undefined,
          excess_return: input.excessReturn ?? undefined,
        },
      };
    })(),
  };
}

/** 面板库内多为「百分数点」：22.87 表示 22.87% */
function panelPct(x?: number | null) {
  if (x == null || Number.isNaN(x)) return null;
  const sign = x > 0 ? "+" : "";
  return `${sign}${x.toFixed(2)}%`;
}

/** IC / RankIC：库内按百分数存（22.87 → 0.2287） */
function panelIc(x?: number | null) {
  if (x == null || Number.isNaN(x)) return null;
  return (x / 100).toFixed(4);
}

export function buildFactorPanelShareDraft(input: {
  name: string;
  factorName: string;
  libraryName?: string | null;
  libraryLabel?: string | null;
  universeLabel?: string;
  periodLabel?: string;
  universeCode?: string;
  periodCode?: string;
  filterLimitUp?: boolean;
  filterLabel?: string;
  metrics?: {
    ic_mean?: number | null;
    rank_ic?: number | null;
    ir?: number | null;
    annual_return?: number | null;
    max_drawdown?: number | null;
    sharpe?: number | null;
    win_rate?: number | null;
    q1_return?: number | null;
    q5_return?: number | null;
    long_short_spread?: number | null;
    q1_turnover?: number | null;
  } | null;
  factorCode?: string | null;
  returnTo?: string;
  returnLabel?: string;
}): CommunityShareDraft {
  const display = (input.name || input.factorName || "因子").trim();
  const fname = (input.factorName || display).trim();
  const title = `【因子面板】${display}`.slice(0, 120);
  const m = input.metrics;
  const meta: string[] = [
    `<p><strong>因子</strong>：${esc(display)}（<code>${esc(fname)}</code>）</p>`,
  ];
  if (input.libraryLabel || input.libraryName) {
    meta.push(
      `<p><strong>因子库</strong>：${esc(input.libraryLabel || String(input.libraryName))}</p>`,
    );
  }
  if (input.universeLabel) {
    meta.push(`<p><strong>股票池</strong>：${esc(input.universeLabel)}</p>`);
  }
  if (input.periodLabel) {
    meta.push(`<p><strong>周期</strong>：${esc(input.periodLabel)}</p>`);
  }
  if (input.filterLabel) {
    meta.push(`<p><strong>涨跌停</strong>：${esc(input.filterLabel)}</p>`);
  }
  const body = [
    "<p>来自因子面板自动摘要。</p>",
    ...meta,
    "<p><strong>指标摘要</strong></p>",
    metricListHtml([
      ["IC均值", panelIc(m?.ic_mean)],
      ["Rank IC", panelIc(m?.rank_ic)],
      ["IR", num(m?.ir)],
      ["年化", panelPct(m?.annual_return)],
      ["最大回撤", panelPct(m?.max_drawdown)],
      ["夏普", num(m?.sharpe)],
      ["胜率", panelPct(m?.win_rate)],
      ["Q1收益", panelPct(m?.q1_return)],
      ["Q5收益", panelPct(m?.q5_return)],
      ["多空价差", panelPct(m?.long_short_spread)],
      ["Q1换手", panelPct(m?.q1_turnover)],
    ]),
    "<blockquote><p>免责声明：内容不构成投资建议。面板指标为聚合缓存，与单次检测参数可能不同。</p></blockquote>",
  ].join("");

  const code = resolveShareFactorCode({
    factorCode: input.factorCode,
    libraryName: input.libraryName,
    factorName: fname,
  });

  const metrics_display: Record<string, string> = {};
  const put = (k: string, v: string | null | undefined) => {
    if (v != null && String(v).trim()) metrics_display[k] = String(v);
  };
  put("IC均值", panelIc(m?.ic_mean) || undefined);
  put("Rank IC", panelIc(m?.rank_ic) || undefined);
  put("IR", num(m?.ir) || undefined);
  put("年化", panelPct(m?.annual_return) || undefined);
  put("最大回撤", panelPct(m?.max_drawdown) || undefined);
  put("夏普", num(m?.sharpe) || undefined);
  put("胜率", panelPct(m?.win_rate) || undefined);
  put("Q1收益", panelPct(m?.q1_return) || undefined);
  put("Q5收益", panelPct(m?.q5_return) || undefined);
  put("多空价差", panelPct(m?.long_short_spread) || undefined);
  put("Q1换手", panelPct(m?.q1_turnover) || undefined);

  const labelParts = [
    "因子面板",
    display,
    input.universeLabel,
    input.periodLabel,
    input.filterLabel,
  ].filter(Boolean);

  return {
    shareDraft: true,
    section: "factor",
    title,
    body,
    code_snippet: code || undefined,
    returnTo: input.returnTo,
    returnLabel: input.returnLabel,
    platform_ref: Object.keys(metrics_display).length
      ? {
          source: "factor_panel",
          label: labelParts.join(" · "),
          factor_name: fname,
          universe: input.universeLabel,
          period: input.periodLabel,
          universe_code: input.universeCode,
          period_code: input.periodCode,
          library: input.libraryName || undefined,
          filter_limit_up: input.filterLimitUp,
          metrics_display,
          metrics: {
            // 展示用小数 IC；库内百分数点 → /100
            ic_mean: m?.ic_mean != null ? m.ic_mean / 100 : undefined,
            rank_ic: m?.rank_ic != null ? m.rank_ic / 100 : undefined,
            ir: m?.ir ?? undefined,
            annual_return: m?.annual_return != null ? m.annual_return / 100 : undefined,
            max_drawdown: m?.max_drawdown != null ? m.max_drawdown / 100 : undefined,
            sharpe: m?.sharpe ?? undefined,
            win_rate: m?.win_rate != null ? m.win_rate / 100 : undefined,
          },
        }
      : undefined,
  };
}
