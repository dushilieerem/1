import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Download, FileSearch, Lock, Sparkles } from "lucide-react";
import { instApi, fmtNum } from "@/lib/instApi";
import { getInstToken } from "@/lib/instAuth";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, PageHeader, StatusBadge } from "./instUi";

type Dim = {
  key: string;
  title: string;
  question?: string;
  status?: string;
  summary?: string;
  checks?: string[];
  counter?: string[];
  evidence_ids?: number[];
};

type Version = {
  id: number;
  version_no: number;
  status: string;
  conclusion?: string;
  six_dim?: Dim[];
  valuation?: Record<string, unknown> | null;
  assumptions?: unknown;
  counter_evidence?: string[];
  open_questions?: string[];
  evidence_ids?: number[];
};

type CaseItem = {
  id: number;
  company_id?: number;
  case_no: string;
  stage: string;
  symbol: string;
  company_name: string;
  market: string;
  industry?: string;
  data_status?: string;
  ref_price?: number;
  versions?: Version[];
  evidence?: Array<{ id: number; title: string; quote?: string; source: string; as_of?: string }>;
  tasks?: Array<{ id: number; title: string; status: string; progress: number }>;
  debates?: Array<{ id: number; status: string; conclusion?: string }>;
};

export function InstResearchPage() {
  const session = useInstSession();
  const { t } = useInstLocale();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const caseId = Number(params.get("case") || 0);
  const [items, setItems] = useState<CaseItem[]>([]);
  const [detail, setDetail] = useState<CaseItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [memo, setMemo] = useState<Record<string, any> | null>(null);
  const [dcf, setDcf] = useState<Record<string, any> | null>(null);
  const [dcfIn, setDcfIn] = useState({
    base_revenue: "100",
    revenue_growth: "10",
    cashflow_margin: "30",
    discount_rate: "10",
    terminal_growth: "2",
    shares: "",
  });
  const runDcf = () => {
    if (!detail?.company_id) return;
    setBusy("dcf");
    setError(null);
    instApi<Record<string, any>>(`/companies/${detail.company_id}/dcf`, {
      method: "POST",
      body: {
        base_revenue: Number(dcfIn.base_revenue),
        revenue_growth: Number(dcfIn.revenue_growth) / 100,
        cashflow_margin: Number(dcfIn.cashflow_margin) / 100,
        discount_rate: Number(dcfIn.discount_rate) / 100,
        terminal_growth: Number(dcfIn.terminal_growth) / 100,
        shares_outstanding: dcfIn.shares ? Number(dcfIn.shares) : undefined,
        years: 5,
      },
    })
      .then(setDcf)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(null));
  };

  const canWrite = (session.permissions.research || "none") === "write";

  const exportReport = async () => {
    setBusy("export");
    setError(null);
    try {
      const token = getInstToken();
      const res = await fetch(`/api/inst/cases/${caseId}/report`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        let message = `导出失败（${res.status}）`;
        try {
          const data = await res.json();
          message = String((data as { detail?: string } | null)?.detail || message);
        } catch {
          /* 非 JSON 错误体，保留默认提示 */
        }
        throw new Error(message);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${detail?.symbol || "research"}-研究简报.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const loadList = () => {
    setLoading(true);
    setError(null);
    instApi<{ items: CaseItem[] }>("/cases")
      .then((data) => setItems(data.items || []))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const loadDetail = (id: number) => {
    setLoading(true);
    setError(null);
    instApi<CaseItem>(`/cases/${id}`)
      .then(setDetail)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (caseId) loadDetail(caseId);
    else {
      setDetail(null);
      loadList();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const version = useMemo<Version | null>(() => {
    const list = detail?.versions || [];
    return list.length ? list[0] : null;
  }, [detail]);

  const evidenceMap = useMemo(() => {
    const map = new Map<number, { title: string; quote?: string; source: string; as_of?: string }>();
    for (const ev of detail?.evidence || []) map.set(ev.id, ev);
    return map;
  }, [detail]);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
      if (caseId) loadDetail(caseId);
      else loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="RESEARCH / 03" title={t("公司研究", "Company research")} />
        <Loading label="正在加载研究案…" />
      </div>
    );
  }

  if (!caseId) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader
          eyebrow="RESEARCH / 03"
          title={t("公司研究", "Company research")}
          desc={t("六维研究、资料包与版本化审核。结论必须带来源与反证条件；未审核通过不能进入辩论。", "Six-dimension research, evidence package and versioned review. Conclusions need sources and falsifiers; debate opens only after approval.")}
        />
        {error ? <ErrorBox message={error} onRetry={loadList} /> : null}
        {items.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {items.map((c) => (
              <Link
                key={c.id}
                to={`/inst/research?case=${c.id}`}
                className="rounded-2xl border border-[#e7e3d8] bg-white p-5 transition hover:border-[#c9a15e]"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-display text-base font-semibold text-slate-900">{c.company_name}</h3>
                    <p className="mt-0.5 font-mono text-[11px] text-slate-500">
                      {c.symbol} · {c.case_no}
                    </p>
                  </div>
                  <StatusBadge status={c.stage} />
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Badge tone="gold">{c.industry || "行业待补充"}</Badge>
                  <StatusBadge status={c.data_status} />
                </div>
                <p className="mt-3 text-xs text-slate-500">
                  点击进入研究案，生成六维结论、资料包与审核记录。
                </p>
              </Link>
            ))}
          </div>
        ) : (
          <Empty>
            <FileSearch className="mx-auto mb-2 h-6 w-6 text-slate-300" />
            还没有研究案。先到「机会发现」选择一家公司并进入研究。
          </Empty>
        )}
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="RESEARCH / 03" title={t("公司研究", "Company research")} />
        <ErrorBox message={error || "研究案不存在"} onRetry={() => loadDetail(caseId)} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="RESEARCH / 03"
        title={detail.company_name}
        desc={`${detail.symbol} · ${detail.industry || "行业待补充"} · ${detail.case_no}`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={() => nav("/inst/research")}>
              <ArrowLeft className="mr-1 h-4 w-4" /> {t("返回列表", "Back to list")}
            </Button>
            <Button variant="ghost" disabled={!!busy} onClick={exportReport}>
              <Download className="mr-1 h-4 w-4" />
              {busy === "export" ? t("导出中…", "Exporting…") : t("导出简报", "Export report")}
            </Button>
            <StatusBadge status={detail.stage} />
          </div>
        }
      />

      {error ? <ErrorBox message={error} onRetry={() => loadDetail(caseId)} /> : null}

      <div className="grid gap-4 lg:grid-cols-[1.55fr_1fr]">
        <div className="space-y-4">
          <Card
            title={t("六维研究", "Six-dimension research")}
            desc={t("每维包含核心问题、数据检查、反证条件与证据 ID；数据不足显示「待补充」，不补造数字。", "Each dimension includes the core question, data checks, falsifiers and evidence IDs. Missing data is marked TBD, never fabricated.")}
            actions={
              <Button
                variant="gold"
                disabled={!canWrite || !!busy}
                onClick={() =>
                  run("generate", () =>
                    instApi(`/cases/${caseId}/research`, { method: "POST", body: { mode: "full" } }),
                  )
                }
              >
                <Sparkles className="mr-1 h-4 w-4" />
                {busy === "generate" ? t("生成中…", "Generating…") : t("生成六维研究", "Generate research")}
              </Button>
            }
          >
            {version?.six_dim?.length ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {version.six_dim.map((dim) => (
                  <article key={dim.key} className="rounded-xl border border-[#f0ece2] bg-[#faf9f5] p-4">
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="text-sm font-semibold text-slate-900">{dim.title}</h3>
                      <StatusBadge status={dim.status} />
                    </div>
                    <p className="mt-1 text-[11px] leading-relaxed text-slate-500">{dim.question}</p>
                    <p className="mt-2 text-xs leading-relaxed text-slate-700">{dim.summary || "待补充"}</p>
                    {dim.checks?.length ? (
                      <ul className="mt-2 space-y-1 text-[11px] text-slate-500">
                        {dim.checks.map((x) => (
                          <li key={x}>· {x}</li>
                        ))}
                      </ul>
                    ) : null}
                    {dim.counter?.length ? (
                      <p className="mt-2 text-[11px] text-amber-700">反证：{dim.counter[0]}</p>
                    ) : null}
                    {dim.evidence_ids?.length ? (
                      <p className="mt-2 font-mono text-[10px] text-slate-400">
                        证据 ID：{dim.evidence_ids.join(", ")}
                      </p>
                    ) : null}
                  </article>
                ))}
              </div>
            ) : (
              <Empty>还没有六维研究。点击右上角生成；生成后自动进入待审核。</Empty>
            )}
          </Card>

          <Card title={t("证据与反证", "Evidence & counter-evidence")} desc={t("重大结论必须可回源；无证据 ID 的结论不能进入审批包。", "Material conclusions must be traceable; conclusions without evidence IDs cannot enter the approval package.")}>
            {detail.evidence?.length ? (
              <ul className="divide-y divide-[#f0ece2]">
                {detail.evidence.map((ev) => (
                  <li key={ev.id} className="py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-slate-800">
                          #{ev.id} {ev.title}
                        </p>
                        <p className="mt-1 text-xs leading-relaxed text-slate-600">{ev.quote || "—"}</p>
                      </div>
                      <div className="shrink-0 text-right">
                        <Badge>{ev.source}</Badge>
                        <p className="mt-1 text-[10px] text-slate-400">{ev.as_of || "—"}</p>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>还没有证据。生成研究会写入行情、估值与财务证据。</Empty>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card title={t("版本与审核", "Version & review")}>
            {version ? (
              <>
                <Field label="版本" value={`v${version.version_no}`} />
                <Field label="状态" value={<StatusBadge status={version.status} />} />
                <Field label="结论" value={version.conclusion || "待补充"} />
                <Field label="证据数" value={`${version.evidence_ids?.length || 0} 条`} />
                <div className="mt-3">
                  <Button
                    variant="ghost"
                    disabled={!!busy || !detail.evidence?.length}
                    onClick={() =>
                      run("memo", async () => {
                        const res = await instApi<{ memo: Record<string, any> }>(`/cases/${caseId}/ai/memo`, {
                          method: "POST",
                        });
                        setMemo(res.memo);
                      })
                    }
                  >
                    {busy === "memo" ? t("生成中…", "Generating…") : t("AI 研究一页纸", "AI research memo")}
                  </Button>
                </div>
                {memo ? (
                  <div className="mt-3 rounded-xl border border-[#c9a15e]/30 bg-[#fbf6ea] p-3 text-xs leading-relaxed text-[#8a6a2f]">
                    <p className="font-medium">AI 摘要（非投资建议）</p>
                    <p className="mt-1">{memo.summary || "—"}</p>
                    {Array.isArray(memo.risks) && memo.risks.length ? (
                      <ul className="mt-2 list-disc pl-4">
                        {memo.risks.map((x: string) => (
                          <li key={x}>{x}</li>
                        ))}
                      </ul>
                    ) : null}
                    {Array.isArray(memo.open_questions) && memo.open_questions.length ? (
                      <p className="mt-2">待核验：{memo.open_questions.join("；")}</p>
                    ) : null}
                  </div>
                ) : null}
                {version.valuation ? (
                  <div className="mt-3 rounded-xl border border-[#c9a15e]/30 bg-[#fbf6ea] p-3 text-xs text-[#8a6a2f]">
                    <p className="font-medium">估值口径</p>
                    <p className="mt-1 leading-relaxed">
                      {String((version.valuation as Record<string, unknown>).note || "演示口径，不是目标价。")}
                    </p>
                  </div>
                ) : null}
                {detail.company_id ? (
                  <div className="mt-3 rounded-xl border border-[#e7e3d8] bg-white p-3">
                    <p className="text-xs font-semibold text-slate-700">
                      五年 DCF（确定性计算 · 不是目标价）
                    </p>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
                      {[
                        ["base_revenue", "基期收入"],
                        ["revenue_growth", "增长率 %"],
                        ["cashflow_margin", "现金流率 %"],
                        ["discount_rate", "折现率 %"],
                        ["terminal_growth", "永续 %"],
                        ["shares", "股本（可选）"],
                      ].map(([key, label]) => (
                        <label key={key} className="space-y-1 text-slate-500">
                          <span>{label}</span>
                          <input
                            value={(dcfIn as Record<string, string>)[key]}
                            onChange={(e) => setDcfIn((v) => ({ ...v, [key]: e.target.value }))}
                            inputMode="decimal"
                            className="w-full rounded-lg border border-[#dcd6c8] bg-[#faf9f5] px-2 py-1 text-xs text-slate-800 outline-none focus:border-[#c9a15e]"
                          />
                        </label>
                      ))}
                    </div>
                    <div className="mt-2">
                      <Button variant="ghost" disabled={!!busy} onClick={runDcf}>
                        {busy === "dcf" ? "计算中…" : "计算估值区间"}
                      </Button>
                    </div>
                    {dcf?.range ? (
                      <div className="mt-2 text-xs leading-relaxed text-slate-600">
                        <p>
                          区间：{fmtNum(dcf.range.low, 2)} – {fmtNum(dcf.range.high, 2)}
                          {dcf.range.base_per_share != null
                            ? `；每股 ${fmtNum(dcf.range.low_per_share, 2)} / ${fmtNum(dcf.range.base_per_share, 2)} / ${fmtNum(dcf.range.high_per_share, 2)}`
                            : ""}
                        </p>
                        {Array.isArray(dcf.limits) ? (
                          <p className="mt-1 text-[11px] text-slate-400">{dcf.limits.join("；")}</p>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {version.status === "pending_review" ? (
                  <div className="mt-4 space-y-2">
                    <textarea
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      placeholder={t("审核意见（退回时必须填写）", "Review comment (required when returning)")}
                      className="min-h-[72px] w-full rounded-lg border border-[#dcd6c8] bg-[#faf9f5] p-2 text-xs outline-none focus:border-[#c9a15e]"
                    />
                    <div className="flex gap-2">
                      <Button
                        variant="gold"
                        disabled={!canWrite || !!busy}
                        onClick={() =>
                          run("approve", () =>
                            instApi(`/research/${version.id}/review`, {
                              method: "POST",
                              body: { decision: "approve", comment },
                            }),
                          )
                        }
                      >
                        {busy === "approve" ? t("提交中…", "Submitting…") : t("审核通过", "Approve")}
                      </Button>
                      <Button
                        variant="danger"
                        disabled={!canWrite || !!busy}
                        onClick={() =>
                          run("return", () =>
                            instApi(`/research/${version.id}/review`, {
                              method: "POST",
                              body: { decision: "return", comment: comment || "退回补充研究" },
                            }),
                          )
                        }
                      >
                        {t("退回", "Return")}
                      </Button>
                    </div>
                  </div>
                ) : null}
                {version.status === "approved" ? (
                  <div className="mt-4">
                    <div className="mb-2 flex items-center gap-2 text-[11px] text-emerald-700">
                      <Lock className="h-3.5 w-3.5" /> 已冻结审核版本，可进入辩论
                    </div>
                    <Button
                      variant="primary"
                      disabled={!canWrite || !!busy}
                      onClick={() => nav(`/inst/debate?case=${caseId}`)}
                    >
                      {t("进入投资辩论", "Enter debate")}
                    </Button>
                  </div>
                ) : null}
              </>
            ) : (
              <Empty>还没有研究版本。</Empty>
            )}
          </Card>

          <Card title={t("研究任务", "Research tasks")} desc={t("任务状态与进度由研究生成流程写入。", "Task status and progress are written by the research pipeline.")}>
            {detail.tasks?.length ? (
              <ul className="space-y-2">
                {detail.tasks.map((t) => (
                  <li key={t.id} className="flex items-center justify-between gap-2 text-sm">
                    <span className="text-slate-700">{t.title}</span>
                    <span className="flex items-center gap-2">
                      <span className="font-mono text-[11px] text-slate-400">{t.progress}%</span>
                      <StatusBadge status={t.status} />
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>生成研究后自动创建六维任务。</Empty>
            )}
          </Card>

          <Card title={t("公司信息", "Company")}>
            <Field label="代码" value={<span className="font-mono">{detail.symbol}</span>} />
            <Field label="市场" value={detail.market} />
            <Field label="行业" value={detail.industry || "待补充"} />
            <Field label="数据状态" value={<StatusBadge status={detail.data_status} />} />
            <Field label="参考价" value={fmtNum(detail.ref_price, 2)} />
          </Card>
        </div>
      </div>

      <p className="text-[11px] leading-relaxed text-slate-400">
        研究结论由数据与规则生成，AI 仅提供解释与反证建议；估值口径为演示，不是目标价。
        数据不足时显示「待补充」，不构成投资建议。
      </p>
    </div>
  );
}
