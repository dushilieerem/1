import type { CommunitySection } from "@/lib/communityApi";

/** 发帖页 location.state 预填（报告分享 / 其它入口） */
export type CommunityShareDraft = {
  shareDraft?: true;
  section?: CommunitySection;
  title?: string;
  /** TipTap 所见即所得：传 HTML，避免编辑器里露出 ** markdown */
  body?: string;
  code_snippet?: string;
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

  return {
    shareDraft: true,
    section: "factor",
    title,
    body,
    code_snippet: (input.factorCode || "").trim() || undefined,
  };
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
  };
}
