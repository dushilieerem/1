import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Download, FileSearch, Loader2, Lock, Sparkles } from "lucide-react";
import { instApi, fmtNum, fmtDateTime } from "@/lib/instApi";
import { getInstToken } from "@/lib/instAuth";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, DataFreshness, Empty, ErrorBox, Field, Loading, PageHeader, StatusBadge, industryLabel } from "./instUi";
import { InstKlineCard } from "./InstKlineCard";

type Dim = {
  key: string;
  title: string;
  question?: string;
  status?: string;
  summary?: string;
  checks?: string[];
  counter?: string[];
  evidence_ids?: number[];
  open_questions?: string[];
  data_gaps?: string[];
  confidence?: number;
  confidence_label?: string;
  rating?: number | null;
  gate?: string | null;
  analysis_md?: string;
  key_numbers?: unknown[];
  falsifiers?: unknown[];
  thesis_links?: unknown[];
  one_line?: string;
  attractiveness?: number | null;
  implication_for_company?: string;
  engine?: string;
  agent?: string;
  agent_error?: string;
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
  industry_analysis?: Dim | null;
  content_hash?: string;
  cutoff?: string;
  frozen_at?: string;
};

type Memo = {
  summary?: string;
  decision?: "proceed" | "watch" | "avoid" | string;
  six_dim_scores?: Array<{ key: string; score: number; confidence?: number; note?: string }>;
  conflicts?: string[];
  key_variables?: string[];
  price_range?: { low?: number | null; base?: number | null; high?: number | null; note?: string } | null;
  holding_period?: string;
  evidence?: string[];
  risks?: string[];
  open_questions?: string[];
  memo_md?: string;
  three_sentences?: { thesis?: string; max_risk?: string; decision?: string };
  price_band?: number[];
  base_value?: number;
  metrics?: Array<{ label: string; value: string; note?: string }>;
  engine?: string;
};

type ChatMessage = { role: "user" | "assistant"; content: string; created_at?: string };

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
  evidence?: Array<{
    id: number;
    title: string;
    quote?: string;
    source: string;
    as_of?: string;
    evidence_type?: string;
    grade?: string;
    event_time?: string;
    available_time?: string;
    document_id?: string;
    page_ref?: string;
    source_uri?: string;
  }>;
  tasks?: Array<{
    id: number;
    task_key?: string;
    title: string;
    status: string;
    progress: number;
    result?: { summary?: string; engine?: string; agent_error?: string };
  }>;
  debates?: Array<{ id: number; status: string; conclusion?: string }>;
};

const AGENT_TITLES: Array<[string, string]> = [
  ["industry", "产业研究"],
  ["business_model", "公司商业模式"],
  ["moat", "护城河"],
  ["financial", "财务质量"],
  ["governance", "CEO 与治理"],
  ["valuation", "估值与价格"],
];

const EVIDENCE_TYPE_META: Record<string, { label: string; note: string; tone: "slate" | "gold" | "green" | "red" | "amber" | "blue" }> = {
  market: { label: "行情", note: "收盘价、估值或交易数据，来自行情库。", tone: "blue" },
  financial: { label: "财务", note: "财报口径的营收、利润、现金流等，需回公告核对。", tone: "green" },
  fact: { label: "事实", note: "行业归属、基础资料等公开事实。", tone: "slate" },
  filing: { label: "公告", note: "公司公告或监管文件摘录。", tone: "amber" },
  news: { label: "新闻", note: "媒体报道，需与公告交叉验证。", tone: "amber" },
  research: { label: "研究", note: "AI Agent 在本次研究中给出的引用。", tone: "gold" },
  counter: { label: "反证", note: "用于推翻结论的反面证据。", tone: "red" },
};

const EVIDENCE_GRADE_META: Record<string, { label: string; note: string; tone: "green" | "gold" | "amber" | "red" }> = {
  A: { label: "A 级", note: "公告/年报/审计报告等一手文件。", tone: "green" },
  B: { label: "B 级", note: "交易所、监管、协会或数据平台口径。", tone: "gold" },
  C: { label: "C 级", note: "第三方研究、券商或权威媒体，需交叉验证。", tone: "amber" },
  D: { label: "D 级", note: "AI 文本、媒体或推断，不能单独支撑结论。", tone: "red" },
};

function clipBrief(value?: string): string {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function sourceLabel(source?: string): string {
  const raw = String(source || "").trim();
  if (!raw) return "来源待补充";
  if (raw.startsWith("ifind")) return "iFinD 行情/财务库";
  if (raw === "eastmoney") return "东方财富";
  if (raw === "agent") return "AI Agent";
  return raw;
}

export function InstResearchPage() {
  const session = useInstSession();
  const { locale, t } = useInstLocale();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const caseId = Number(params.get("case") || 0);
  const [items, setItems] = useState<CaseItem[]>([]);
  const [detail, setDetail] = useState<CaseItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [returnOpen, setReturnOpen] = useState(false);
  const [returnTargets, setReturnTargets] = useState<string[]>(["industry", ...AGENT_TITLES.map(([key]) => key)]);
  const [returnError, setReturnError] = useState<string | null>(null);
  const [memo, setMemo] = useState<Memo | null>(null);
  const [memoBusy, setMemoBusy] = useState(false);
  const autoRan = useRef(false);
  const memoRan = useRef(false);
  const chatLoaded = useRef<Set<string>>(new Set());
  const [activeDim, setActiveDim] = useState("industry");
  const [dimBusy, setDimBusy] = useState<string | null>(null);
  const [chats, setChats] = useState<Record<string, ChatMessage[]>>({});
  const [chatInput, setChatInput] = useState<Record<string, string>>({});
  const [chatBusy, setChatBusy] = useState<string | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);

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
        let message = `${t("导出失败", "Export failed")}（${res.status}）`;
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
      a.download = `${detail?.symbol || "research"}-${t("研究简报", "research-report")}.md`;
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

  const dims = useMemo<Dim[]>(() => version?.six_dim || [], [version]);
  const activeDimData = useMemo<Dim | null>(
    () => dims.find((d) => d.key === activeDim) || dims[0] || null,
    [dims, activeDim],
  );
  const latestEvidenceDate = useMemo(() => {
    const dates = (detail?.evidence || [])
      .map((e) => e.as_of)
      .filter((d): d is string => Boolean(d))
      .sort();
    return dates.length ? dates[dates.length - 1] : null;
  }, [detail]);
  useEffect(() => {
    if (dims.length && !dims.some((d) => d.key === activeDim)) {
      setActiveDim(dims[0].key);
    }
  }, [dims, activeDim]);

  useEffect(() => {
    if (!evidenceOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setEvidenceOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [evidenceOpen]);

  // 版本更新（六维重生成/单维重分析）后，旧一页纸作废，重新生成。
  useEffect(() => {
    setMemo(null);
    memoRan.current = false;
  }, [version?.id]);

  const loadMemo = async (refresh = false) => {
    setMemoBusy(true);
    try {
      const res = await instApi<{ memo: Memo }>(`/cases/${caseId}/ai/memo`, {
        method: "POST",
        body: { refresh },
      });
      setMemo(res.memo);
    } finally {
      setMemoBusy(false);
    }
  };

  const autopilot = async () => {
    setBusy("auto");
    setError(null);
    try {
      await instApi(`/cases/${caseId}/research`, { method: "POST", body: { mode: "full" } });
      const next = await instApi<CaseItem>(`/cases/${caseId}`);
      setDetail(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    if (!caseId || !detail || !canWrite || version || autoRan.current) return;
    autoRan.current = true;
    void autopilot();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, detail, version, canWrite]);

  useEffect(() => {
    if (!caseId || !detail || !version || memo || memoRan.current || !canWrite) return;
    memoRan.current = true;
    void loadMemo().catch(() => {
      /* 自动摘要失败时保留手动按钮 */
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, detail, version, memo, canWrite]);

  useEffect(() => {
    const key = activeDimData?.key;
    if (!caseId || !key || chatLoaded.current.has(key)) return;
    chatLoaded.current.add(key);
    instApi<{ items: ChatMessage[] }>(`/cases/${caseId}/dimensions/${key}/chat`)
      .then((res) => {
        if (!res.items?.length) return;
        setChats((prev) => ({ ...prev, [key]: res.items }));
      })
      .catch(() => {
        /* 历史加载失败不影响新提问 */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, activeDimData?.key]);

  useEffect(() => {
    if (busy !== "auto" || !caseId) return;
    let alive = true;
    const timer = window.setInterval(() => {
      instApi<CaseItem>(`/cases/${caseId}`)
        .then((next) => {
          if (alive) setDetail(next);
        })
        .catch(() => {
          /* 轮询失败不打断主请求 */
        });
    }, 2000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [busy, caseId]);

  const taskByKey = useMemo(() => {
    const map = new Map<string, NonNullable<CaseItem["tasks"]>[number]>();
    for (const t of detail?.tasks || []) {
      if (t.task_key) map.set(t.task_key, t);
    }
    return map;
  }, [detail]);
  const hasLiveTasks = (detail?.tasks || []).some((t) => t.status === "pending" || t.status === "running");

  const regenDim = async (key: string) => {
    setDimBusy(key);
    setError(null);
    try {
      await instApi(`/cases/${caseId}/research`, { method: "POST", body: { mode: key } });
      const next = await instApi<CaseItem>(`/cases/${caseId}`);
      setDetail(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDimBusy(null);
    }
  };

  const sendChat = async (key: string) => {
    const question = (chatInput[key] || "").trim();
    if (!question || chatBusy) return;
    const history = chats[key] || [];
    setChats((prev) => ({ ...prev, [key]: [...(prev[key] || []), { role: "user", content: question }] }));
    setChatInput((prev) => ({ ...prev, [key]: "" }));
    setChatBusy(key);
    setError(null);
    try {
      const res = await instApi<{ answer: string }>(`/cases/${caseId}/dimensions/${key}/chat`, {
        method: "POST",
        body: {
          question,
          history: history.slice(-6),
          client_message_id:
            typeof crypto !== "undefined" && "randomUUID" in crypto
              ? crypto.randomUUID()
              : `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        },
      });
      setChats((prev) => ({
        ...prev,
        [key]: [...(prev[key] || []), { role: "assistant", content: res.answer }],
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setChatBusy(null);
    }
  };

  const submitReturn = async () => {
    if (!version) return;
    const reason = comment.trim();
    if (!reason) {
      setReturnError(t("请填写退回原因。", "A return reason is required."));
      return;
    }
    if (!returnTargets.length) {
      setReturnError(t("请至少选择一个要退回的板块或维度。", "Select at least one section or dimension to return."));
      return;
    }
    setBusy("return");
    setError(null);
    setReturnError(null);
    try {
      const next = await instApi<CaseItem>(`/research/${version.id}/review`, {
        method: "POST",
        body: { decision: "return", comment: reason, targets: returnTargets },
      });
      setDetail(next);
      setReturnOpen(false);
      setComment("");
    } catch (e) {
      setReturnError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const approveAndDebate = async () => {
    if (!version) return;
    setBusy("approve");
    setError(null);
    try {
      await instApi(`/research/${version.id}/review`, {
        method: "POST",
        body: { decision: "approve", comment },
      });
      nav(`/inst/debate?case=${caseId}&autostart=1`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(null);
    }
  };

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
        <Loading label={t("正在加载研究案…", "Loading research case…")} />
      </div>
    );
  }

  if (!caseId) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader
          eyebrow="RESEARCH / 03"
          title={t("公司研究", "Company research")}
          desc={t("6 个 Agent 分别从产业、商业模式、护城河、财务、治理、估值独立分析，汇总后生成 AI 一页纸；审核通过后自动开始 AI 辩论。", "Six agents analyze industry, business model, moat, financials, governance and valuation independently, then an AI memo is generated; approval auto-starts the AI debate.")}
        />
        {error ? <ErrorBox message={error} onRetry={loadList} /> : null}
        {items.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {items.map((c) => (
              <Link
                key={c.id}
                to={`/inst/research?case=${c.id}`}
                className="rounded-xl border border-[#dde5f2] bg-white p-5 transition hover:border-[#7950ba]"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-display text-base font-semibold text-[#171923]">{c.company_name}</h3>
                    <p className="mt-0.5 font-mono text-[11px] text-[#68738b]">
                      {c.symbol} · {c.case_no}
                    </p>
                  </div>
                  <StatusBadge status={c.stage} />
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Badge tone="gold">{c.industry || t("行业待补充", "Industry n/a")}</Badge>
                  <StatusBadge status={c.data_status} />
                </div>
                <p className="mt-3 text-xs text-[#68738b]">
                  {t("点击进入研究案，生成六维结论、资料包与审核记录。", "Open the case to generate six dimensions, the evidence pack and reviews.")}
                </p>
              </Link>
            ))}
          </div>
        ) : (
          <Empty>
            <FileSearch className="mx-auto mb-2 h-6 w-6 text-[#a9a4bd]" />
            {t("还没有研究案。先到「机会发现」选择一家公司并进入研究。", "No research cases yet. Pick a company in Discovery and start research.")}
          </Empty>
        )}
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        <PageHeader eyebrow="RESEARCH / 03" title={t("公司研究", "Company research")} />
        <ErrorBox message={error || t("研究案不存在", "Research case not found")} onRetry={() => loadDetail(caseId)} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="RESEARCH / 03"
        title={detail.company_name}
        desc={t("六维分析、AI 一页纸与证据链；审核通过后自动进入辩论。", "Six dimensions, AI one-pager and evidence chain; approval starts the debate automatically.")}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={() => nav("/inst/research")}>
              <ArrowLeft className="mr-1 h-4 w-4" /> {t("返回列表", "Back to list")}
            </Button>
            <Button
              variant="ghost"
              onClick={() => setEvidenceOpen(true)}
              title={t("查看证据类型、来源、数据日期与原文摘录", "View evidence types, sources, dates and quotes")}
            >
              <FileSearch className="mr-1 h-4 w-4" />
              {t("证据与反证", "Evidence")}（{detail.evidence?.length || 0}）
            </Button>
            <Button variant="ghost" disabled={!!busy} onClick={exportReport}>
              <Download className="mr-1 h-4 w-4" />
              {busy === "export" ? t("导出中…", "Exporting…") : t("导出简报", "Export report")}
            </Button>
            <DataFreshness date={latestEvidenceDate} label={t("证据日", "Evidence")} />
            <StatusBadge status={detail.stage} />
          </div>
        }
      />

      <Card
        title={t("公司信息", "Company")}
        actions={<Badge tone="gold">{detail.case_no}</Badge>}
      >
        <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 xl:grid-cols-5">
          <div>
            <p className="text-[10px] text-[#77718c]">{t("代码", "Symbol")}</p>
            <p className="mt-0.5 font-mono text-sm font-medium text-[#171923]">{detail.symbol}</p>
          </div>
          <div>
            <p className="text-[10px] text-[#77718c]">{t("市场", "Market")}</p>
            <p className="mt-0.5 text-sm font-medium text-[#171923]">{detail.market || t("待补充", "TBD")}</p>
          </div>
          <div>
            <p className="text-[10px] text-[#77718c]">{t("行业", "Industry")}</p>
            <p className="mt-0.5 text-sm font-medium text-[#171923]">{industryLabel(detail.industry, locale)}</p>
          </div>
          <div>
            <p className="text-[10px] text-[#77718c]">{t("数据状态", "Data status")}</p>
            <p className="mt-1"><StatusBadge status={detail.data_status} /></p>
          </div>
          <div>
            <p className="text-[10px] text-[#77718c]">{t("参考价（CNY）", "Reference price (CNY)")}</p>
            <p className="mt-0.5 font-mono text-sm font-medium text-[#171923]">{fmtNum(detail.ref_price, 2)}</p>
          </div>
        </div>
        {detail.data_status && detail.data_status !== "real" ? (
          <p className="mt-3 border-t border-[#e3eaf8] pt-2 text-[10px] leading-relaxed text-[#77718c]">
            {t(
              "数据状态“待补充”表示财务、公告或行业数据不完整；相关维度会标记数据缺口，但流程仍可继续。",
              "Data status 'Partial' means financial, filing or industry data is incomplete; affected dimensions mark data gaps but the workflow can continue.",
            )}
          </p>
        ) : null}
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card
          title={t("行业分析（独立板块）", "Industry analysis (standalone)")}
          desc={t("不属于六维；只研究行业空间、周期、产业链与竞争格局，为六维和一页纸提供行业底图。", "Not one of the six dimensions; it covers industry space, cycle, chain and competition as the industry base for the six dimensions and the one-pager.")}
          actions={
            version?.industry_analysis ? (
              <div className="flex flex-wrap gap-1.5">
                <StatusBadge status={version.industry_analysis.status} />
                <Badge tone={version.industry_analysis.engine === "agent" ? "gold" : "slate"}>
                  {version.industry_analysis.engine === "agent" ? t("AI Agent", "AI Agent") : t("规则兜底", "Rule fallback")}
                </Badge>
                {version.industry_analysis.attractiveness != null ? (
                  <Badge tone={version.industry_analysis.gate === "fail" ? "red" : version.industry_analysis.gate === "watch" ? "amber" : "green"}>
                    {`${t("吸引力", "Attractiveness")} ${version.industry_analysis.attractiveness}/5`}
                  </Badge>
                ) : null}
              </div>
            ) : null
          }
        >
          {version?.industry_analysis ? (
            <div className="space-y-2">
              <p className="text-xs leading-relaxed text-[#505369]">
                {clipBrief(version.industry_analysis.summary) || t("待补充", "TBD")}
              </p>
              {version.industry_analysis.checks?.length ? (
                <ul className="space-y-1 text-[11px] leading-relaxed text-[#68738b]">
                  {version.industry_analysis.checks.slice(0, 5).map((item) => (
                    <li key={item}>· {clipBrief(item)}</li>
                  ))}
                </ul>
              ) : null}
              {version.industry_analysis.counter?.length ? (
                <p className="text-[11px] leading-relaxed text-amber-700">
                  {t("反证", "Falsifier")}：{clipBrief(version.industry_analysis.counter[0])}
                </p>
              ) : null}
              {version.industry_analysis.data_gaps?.length ? (
                <p className="text-[10px] leading-relaxed text-[#77718c]">
                  {t("数据缺口", "Data gaps")}：{version.industry_analysis.data_gaps.map(clipBrief).join("；")}
                </p>
              ) : null}
              <p className="text-[10px] text-[#77718c]">
                {t("证据", "Evidence")}：{version.industry_analysis.evidence_ids?.length || 0} {t("条", "items")}
              </p>
              {version.industry_analysis.analysis_md ? (
                <details className="rounded-lg border border-[#e3eaf8] bg-white px-3 py-2">
                  <summary className="cursor-pointer text-[11px] font-medium text-[#7950ba]">
                    {t("完整行业分析", "Full industry analysis")}
                  </summary>
                  <div className="mt-2 whitespace-pre-wrap text-[11px] leading-relaxed text-[#505369]">
                    {version.industry_analysis.analysis_md}
                  </div>
                </details>
              ) : null}
            </div>
          ) : (
            <Empty>
              {busy === "auto"
                ? t("行业分析生成中…", "Generating industry analysis…")
                : t("还没有独立行业分析；生成六维分析后自动生成。", "No standalone industry analysis yet; it is generated with the six dimensions.")}
            </Empty>
          )}
        </Card>
        <InstKlineCard companyId={Number(detail.company_id || 0)} symbol={detail.symbol} />
      </div>

      {error ? <ErrorBox message={error} onRetry={() => loadDetail(caseId)} /> : null}

      {detail.market && detail.market !== "CN" ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-[12px] leading-relaxed text-amber-800">
          {t(
            "美股/港股暂无财务、公告、行业与指数数据源，只有行情；六维结论会标注数据缺口，仅用于流程演示。",
            "No fundamental, filing, industry or index data source for US/HK; prices only. Dimensions will mark data gaps and are for workflow demo only.",
          )}
        </div>
      ) : null}

      {busy === "auto" || hasLiveTasks ? (
        <Card
          title={version ? t("6 个 Agent 实时进度", "6 agents live progress") : t("6 个 Agent 正在生成", "Generating with 6 agents")}
          desc={t("每个 Agent 独立分析，完成后立即显示该维结论；全部完成后再生成 AI 一页纸。", "Each agent analyzes independently; its conclusion appears as soon as it finishes, followed by the AI memo.")}
        >
          <div className="grid gap-2 sm:grid-cols-2">
            {AGENT_TITLES.map(([key, label]) => {
              const task = taskByKey.get(key);
              const status = task?.status || "pending";
              const running = status === "running";
              const done = status === "done" || status === "needs_review";
              return (
                <div key={key} className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2 text-xs font-medium text-[#252533]">
                      {running ? <Loader2 className="h-3.5 w-3.5 animate-spin text-[#7950ba]" /> : null}
                      {label}
                    </span>
                    <StatusBadge status={status} />
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed text-[#68738b]">
                    {done && task?.result?.summary
                      ? task.result.summary
                      : status === "failed"
                        ? task?.result?.agent_error || t("该 Agent 失败，稍后回退规则模板", "Agent failed; fallback will be used")
                        : running
                          ? t("分析中…", "Analyzing…")
                          : t("等待启动…", "Waiting…")}
                  </p>
                </div>
              );
            })}
          </div>
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1.55fr_1fr]">
        <div className="space-y-4">
          <Card
            title={t("六维分析", "Six-dimension analysis")}
            desc={t("按目录切换六个维度；单维可单独分析、向 AI 追问。AI 一页纸在下方单独展示，整体审核在右侧一次完成。", "Switch between the six dimensions; each can be re-analyzed or queried. The AI one-pager is shown separately below, and final approval is done once on the right.")}
            actions={
              <div className="flex flex-wrap items-center justify-end gap-2">
                <div role="tablist" aria-label={t("维度目录", "Dimension directory")} className="flex flex-wrap gap-1">
                  {AGENT_TITLES.map(([key, label]) => {
                    const selected = (activeDimData?.key || activeDim) === key;
                    return (
                      <button
                        key={key}
                        type="button"
                        role="tab"
                        aria-selected={selected}
                        onClick={() => setActiveDim(key)}
                        className={`rounded-md border px-2 py-1 text-[11px] transition ${
                          selected
                            ? "border-[#b42345] bg-[#fbe9ef] text-[#a31f42]"
                            : "border-[#dde5f2] bg-white text-[#68738b] hover:border-[#7950ba]"
                        }`}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
                <Button
                  variant="gold"
                  disabled={!canWrite || !!busy || !!dimBusy}
                  onClick={() => void autopilot()}
                >
                  <Sparkles className="mr-1 h-4 w-4" />
                  {busy === "auto"
                    ? version
                      ? t("6 个 Agent 重新生成中…", "Regenerating with 6 agents…")
                      : t("6 个 Agent 正在生成中…", "Generating with 6 agents…")
                    : version
                      ? t("重新生成六维分析", "Regenerate six-dimension analysis")
                      : t("生成六维分析", "Generate six-dimension analysis")}
                </Button>
              </div>
            }
          >
            {activeDimData ? (
              <div className="space-y-3">
                {activeDimData.engine === "rule" && activeDimData.agent_error ? (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-800">
                    {t(
                      "AI 未配置或本次分析失败，本维已回退规则模板；结论仍可审核，但关键数据需人工补充。",
                      "AI is unavailable or this run failed; this dimension used the rule template. The conclusion can still be reviewed, but key data needs manual input.",
                    )}
                  </div>
                ) : null}
                <article className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-4">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-sm font-semibold text-[#171923]">{activeDimData.title}</h3>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <StatusBadge status={activeDimData.status} />
                      <Badge tone={activeDimData.engine === "agent" ? "gold" : "slate"}>
                        {activeDimData.engine === "agent"
                          ? `AI Agent${activeDimData.confidence != null ? ` · ${activeDimData.confidence.toFixed(2)}` : ""}`
                          : t("规则兜底", "Rule fallback")}
                      </Badge>
                      {activeDimData.rating != null ? (
                        <Badge tone={activeDimData.gate === "fail" ? "red" : activeDimData.gate === "watch" ? "amber" : "green"}>
                          {`${t("评级", "Rating")} ${activeDimData.rating}/5${activeDimData.gate ? ` · ${activeDimData.gate}` : ""}`}
                        </Badge>
                      ) : null}
                    </div>
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed text-[#68738b]">{activeDimData.question}</p>
                  <p className="mt-2 text-xs leading-relaxed text-[#505369]">{clipBrief(activeDimData.summary) || t("待补充", "TBD")}</p>
                  {activeDimData.analysis_md ? (
                    <details className="mt-2 rounded-lg border border-[#e3eaf8] bg-white px-3 py-2">
                      <summary className="cursor-pointer text-[11px] font-medium text-[#7950ba]">
                        {t("完整分析", "Full analysis")}
                      </summary>
                      <div className="mt-2 whitespace-pre-wrap text-[11px] leading-relaxed text-[#505369]">
                        {activeDimData.analysis_md}
                      </div>
                    </details>
                  ) : null}
                  {activeDimData.checks?.length ? (
                    <ul className="mt-2 space-y-1 text-[11px] text-[#68738b]">
                      {activeDimData.checks.map((x) => (
                        <li key={x}>· {x}</li>
                      ))}
                    </ul>
                  ) : null}
                  {activeDimData.counter?.length ? (
                    <p className="mt-2 text-[11px] text-amber-700">{t("反证", "Falsifier")}：{activeDimData.counter[0]}</p>
                  ) : null}
                  {activeDimData.data_gaps?.length ? (
                    <p className="mt-2 text-[11px] text-[#68738b]">{t("数据缺口", "Data gaps")}：{activeDimData.data_gaps.join("；")}</p>
                  ) : null}
                  {activeDimData.agent_error ? (
                    <p
                      className="mt-2 text-[11px] text-amber-700"
                      title={String(activeDimData.agent_error)}
                    >
                      {t(
                        "AI 分析未完成，已使用规则模板；技术原因可悬停查看。",
                        "AI analysis did not complete; the rule template was used. Hover for the technical reason.",
                      )}
                    </p>
                  ) : null}
                  {activeDimData.evidence_ids?.length ? (
                    <p className="mt-2 font-mono text-[10px] text-[#77718c]">
                      {t("证据 ID", "Evidence IDs")}：{activeDimData.evidence_ids.join(", ")}
                    </p>
                  ) : null}
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <Button
                      variant="ghost"
                      disabled={!canWrite || !!busy || !!dimBusy}
                      onClick={() => void regenDim(activeDimData.key)}
                    >
                      {dimBusy === activeDimData.key
                        ? t("该维度分析中…", "Analyzing this dimension…")
                        : t("单独分析该维度", "Analyze this dimension")}
                    </Button>
                    {dimBusy === activeDimData.key ? (
                      <span className="text-[11px] text-[#7950ba]">
                        {t("只更新本维，其余五维保留", "Only this dimension is updated; the other five are kept")}
                      </span>
                    ) : null}
                  </div>
                </article>

                <div className="rounded-xl border border-[#e3eaf8] bg-white p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-semibold text-[#505369]">
                      {t("向 AI 追问（仅限本维度）", "Ask AI (this dimension only)")}
                    </p>
                    <Badge tone="gold">{t("AI 对话", "AI chat")}</Badge>
                  </div>
                  <div className="mt-2 max-h-64 space-y-2 overflow-y-auto">
                    {(chats[activeDimData.key] || []).length ? (
                      (chats[activeDimData.key] || []).map((m, i) => (
                        <div
                          key={`${m.role}-${i}`}
                          className={`rounded-lg px-3 py-2 text-xs leading-relaxed ${
                            m.role === "user"
                              ? "ml-8 bg-[#f2eafa] text-[#5a3d85]"
                              : "mr-8 bg-[#f8faff] text-[#505369]"
                          }`}
                        >
                          {m.content}
                        </div>
                      ))
                    ) : (
                      <p className="text-[11px] text-[#77718c]">
                        {t(
                          "可以问：关键反证是什么？哪些数据还缺失？",
                          "Ask: what is the key falsifier? What data is missing?",
                        )}
                      </p>
                    )}
                  </div>
                  <div className="mt-2 flex gap-2">
                    <input
                      value={chatInput[activeDimData.key] || ""}
                      onChange={(e) =>
                        setChatInput((prev) => ({ ...prev, [activeDimData.key]: e.target.value }))
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          void sendChat(activeDimData.key);
                        }
                      }}
                      placeholder={t("向 AI 提出关于本维度的问题…", "Ask a question about this dimension…")}
                      className="min-w-0 flex-1 rounded-lg border border-[#dde5f2] bg-[#f8faff] px-2 py-1.5 text-xs outline-none focus:border-[#7950ba]"
                    />
                    <Button
                      variant="ghost"
                      disabled={!chatInput[activeDimData.key]?.trim() || chatBusy === activeDimData.key}
                      onClick={() => void sendChat(activeDimData.key)}
                    >
                      {chatBusy === activeDimData.key ? t("回答中…", "Answering…") : t("发送", "Send")}
                    </Button>
                  </div>
                </div>
              </div>
            ) : (
              <Empty>{t("正在自动开展六维分析；如未开始，可点击右上角。", "Six-dimension analysis starts automatically; use the top-right button if needed.")}</Empty>
            )}
          </Card>

        </div>

        <div className="space-y-4">
          <Card title={t("版本与审核", "Version & review")}>
            {version ? (
              <>
                <Field label={t("版本", "Version")} value={`v${version.version_no}`} />
                <Field label={t("状态", "Status")} value={<StatusBadge status={version.status} />} />
                <Field label={t("结论", "Conclusion")} value={version.conclusion || t("待补充", "TBD")} />
                <Field label={t("证据数", "Evidence")} value={`${version.evidence_ids?.length || 0} ${t("条", "items")}`} />
                <Field label={t("截止日", "Cutoff")} value={version.cutoff || t("待补充", "TBD")} />
                <Field
                  label={t("内容 hash", "Content hash")}
                  value={
                    version.content_hash ? (
                      <span className="font-mono text-[10px]" title={version.content_hash}>
                        {version.content_hash.slice(0, 12)}…
                      </span>
                    ) : (
                      t("待补充", "TBD")
                    )
                  }
                />
                <Field
                  label={t("冻结时间", "Frozen at")}
                  value={version.frozen_at ? fmtDateTime(version.frozen_at) : t("未冻结", "Not frozen")}
                />
                {version.valuation ? (
                  <div className="mt-3 rounded-xl border border-[#7950ba]/30 bg-[#f2eafa] p-3 text-xs text-[#b42345]">
                    <p className="font-medium">{t("估值口径", "Valuation basis")}</p>
                    <p className="mt-1 leading-relaxed">
                      {String((version.valuation as Record<string, unknown>).note || t("演示口径，不是目标价。", "Demo basis, not a target price."))}
                    </p>
                  </div>
                ) : null}
                {version.status === "pending_review" ? (
                  <div className="mt-4 space-y-2">
                    <textarea
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      placeholder={t("审核意见（退回时必须填写）", "Review comment (required when returning)")}
                      className="min-h-[72px] w-full rounded-lg border border-[#dde5f2] bg-[#f8faff] p-2 text-xs outline-none focus:border-[#7950ba]"
                    />
                    <div className="flex flex-wrap items-center gap-2">
                      <Button
                        variant="gold"
                        disabled={!canWrite || !!busy}
                        onClick={() => void approveAndDebate()}
                      >
                        {busy === "approve" ? t("提交中…", "Submitting…") : t("审核通过", "Approve")}
                      </Button>
                      <Button
                        variant="danger"
                        disabled={!canWrite || !!busy}
                        onClick={() => {
                          setReturnError(null);
                          setReturnOpen(true);
                        }}
                      >
                        {busy === "return" ? t("重跑中…", "Rerunning…") : t("退回并重跑", "Return & rerun")}
                      </Button>
                    </div>
                  </div>
                ) : null}
                {version.status === "approved" ? (
                  <div className="mt-4">
                    <div className="mb-2 flex items-center gap-2 text-[11px] text-emerald-700">
                      <Lock className="h-3.5 w-3.5" /> {t("已冻结审核版本，可进入辩论", "Approved version is frozen; debate can start")}
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
              <Empty>{t("还没有研究版本。", "No research versions yet.")}</Empty>
            )}
          </Card>

        </div>
      </div>

      <Card
        title={t("AI 一页纸", "AI one-pager")}
        desc={t("按六维结构输出：总结结论、关键指标、六维要点、核心风险与下一步核验。", "Structured one-pager: summary, key metrics, six dimension highlights, key risks and next checks.")}
        actions={
          <Button
            variant="ghost"
            disabled={!!busy || memoBusy}
            onClick={() => {
              void loadMemo(true).catch((e: Error) => setError(e.message));
            }}
          >
            {memoBusy
              ? t("生成中…", "Generating…")
              : memo
                ? t("重新生成一页纸", "Regenerate one-pager")
                : t("生成 AI 一页纸", "Generate AI one-pager")}
          </Button>
        }
      >
        {memo ? (
          <div className="rounded-2xl border border-[#e3eaf8] bg-white p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="font-display text-xl font-semibold text-[#171923]">
                  {detail.company_name}{" "}
                  <span className="font-mono text-sm font-normal text-[#68738b]">（{detail.symbol}）</span>
                </h3>
                <p className="mt-1 text-[11px] text-[#77718c]">
                  {t("AI 投资研究摘要 · 六维分析", "AI investment research summary · six dimensions")}
                </p>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-1.5">
                {memo.decision ? (
                  <Badge
                    tone={
                      memo.decision === "proceed" ? "green" : memo.decision === "avoid" ? "red" : "amber"
                    }
                  >
                    {memo.decision === "proceed"
                      ? t("研究建议：推进辩论", "Research: proceed")
                      : memo.decision === "avoid"
                        ? t("研究建议：回避", "Research: avoid")
                        : t("研究建议：观察", "Research: watch")}
                  </Badge>
                ) : null}
                <Badge tone="gold">{version?.conclusion || t("待补充研究", "Research TBD")}</Badge>
              </div>
            </div>

            <section className="mt-4">
              <h4 className="text-sm font-semibold text-[#171923]">{t("总结结论", "Summary")}</h4>
              <p className="mt-1 text-xs leading-relaxed text-[#505369]">
                {clipBrief(memo.summary) || t("待补充", "TBD")}
              </p>
              {memo.memo_md ? (
                <details className="mt-2 rounded-lg border border-[#e3eaf8] bg-[#f8faff] px-3 py-2">
                  <summary className="cursor-pointer text-[11px] font-medium text-[#7950ba]">
                    {t("完整一页纸与六张表", "Full one-pager and tables")}
                  </summary>
                  <div className="mt-2 whitespace-pre-wrap text-[11px] leading-relaxed text-[#505369]">
                    {memo.memo_md}
                  </div>
                </details>
              ) : null}
            </section>

            {memo.price_range || memo.holding_period ? (
              <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-[#e3eaf8] bg-[#f8faff] px-3 py-2 text-xs text-[#505369]">
                {memo.price_range ? (
                  <span>
                    {t("研究估值区间", "Research valuation range")}：
                    <span className="font-mono">
                      {fmtNum(memo.price_range.low, 2)} – {fmtNum(memo.price_range.high, 2)}
                      {memo.price_range.base != null ? `（${t("基准", "base")} ${fmtNum(memo.price_range.base, 2)}）` : ""}
                    </span>
                  </span>
                ) : null}
                {memo.holding_period ? (
                  <span>
                    {t("建议持有期", "Holding period")}：{memo.holding_period}
                  </span>
                ) : null}
                <span className="text-[10px] text-[#77718c]">{t("研究区间，不是目标价或收益承诺。", "Research range, not a target price or return promise.")}</span>
              </div>
            ) : null}

            {memo.metrics?.length ? (
              <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {memo.metrics.map((m) => (
                  <div key={m.label} className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-3">
                    <p className="text-[10px] text-[#77718c]">{m.label}</p>
                    <p className="mt-1 font-display text-lg font-semibold text-[#171923]">{m.value}</p>
                    {m.note ? <p className="mt-0.5 text-[10px] text-[#68738b]">{m.note}</p> : null}
                  </div>
                ))}
              </div>
            ) : null}
            <p className="mt-2 text-[10px] leading-relaxed text-[#77718c]">
              {t(
                "口径：营收/净利为最近报告期，同比为报告期同比；ROE 为报告期口径；PE TTM 为滚动市盈率，历史分位取近 3 年。缺失指标不展示，不代表为 0。",
                "Definitions: revenue/net profit are the latest reporting period, YoY is period-over-period; ROE is the reporting-period ratio; PE TTM is trailing twelve months and its percentile uses the last 3 years. Missing metrics are omitted, not treated as zero.",
              )}
            </p>

            {memo.six_dim_scores?.length ? (
              <section className="mt-4">
                <h4 className="text-sm font-semibold text-[#171923]">{t("六维评分（1-5）", "Six-dimension scores (1-5)")}</h4>
                <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {memo.six_dim_scores.map((score) => (
                    <div key={score.key} className="rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-medium text-[#505369]">
                          {AGENT_TITLES.find(([key]) => key === score.key)?.[1] || score.key}
                        </span>
                        <span className="font-display text-lg font-semibold text-[#171923]">
                          {score.score.toFixed(1)}
                        </span>
                      </div>
                      {score.note ? (
                        <p className="mt-1 text-[10px] leading-relaxed text-[#68738b]">{score.note}</p>
                      ) : null}
                      {score.confidence != null ? (
                        <p className="mt-1 font-mono text-[10px] text-[#77718c]">
                          {t("置信度", "Confidence")} {Number(score.confidence).toFixed(2)}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </div>
              </section>
            ) : null}

            {memo.conflicts?.length ? (
              <section className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3">
                <h4 className="text-sm font-semibold text-amber-900">{t("未解决分歧", "Unresolved conflicts")}</h4>
                <ul className="mt-1 space-y-1 text-[11px] leading-relaxed text-amber-800">
                  {memo.conflicts.map((conflict, index) => (
                    <li key={`${index}-${conflict}`}>· {clipBrief(conflict)}</li>
                  ))}
                </ul>
              </section>
            ) : null}

            {memo.key_variables?.length ? (
              <section className="mt-4">
                <h4 className="text-sm font-semibold text-[#171923]">{t("关键变量", "Key variables")}</h4>
                <ul className="mt-1 space-y-1 text-[11px] leading-relaxed text-[#505369]">
                  {memo.key_variables.map((variable, index) => (
                    <li key={`${index}-${variable}`}>· {clipBrief(variable)}</li>
                  ))}
                </ul>
              </section>
            ) : null}

            <div className="mt-5 space-y-4">
              {dims.map((d, i) => (
                <section key={d.key} className="border-t border-[#e3eaf8] pt-4">
                  <h4 className="text-xs font-semibold text-[#171923]">
                    {String(i + 1).padStart(2, "0")} {d.title}
                  </h4>
                  <ul className="mt-2 space-y-1 text-[11px] leading-relaxed text-[#505369]">
                    <li>· {clipBrief(d.summary) || t("待补充", "TBD")}</li>
                    {d.counter?.[0] ? (
                      <li>· {t("关键问题", "Key question")}：{d.counter[0]}</li>
                    ) : d.checks?.[0] ? (
                      <li>· {d.checks[0]}</li>
                    ) : null}
                  </ul>
                </section>
              ))}
            </div>

            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <section className="border-t border-[#e3eaf8] pt-4">
                <h4 className="text-xs font-semibold text-[#171923]">{t("核心关注风险", "Key risks")}</h4>
                {memo.risks?.length ? (
                  <ol className="mt-2 list-decimal space-y-1 pl-4 text-[11px] leading-relaxed text-[#505369]">
                    {memo.risks.map((x) => (
                      <li key={x}>{clipBrief(x)}</li>
                    ))}
                  </ol>
                ) : (
                  <p className="mt-2 text-[11px] text-[#77718c]">{t("待补充", "TBD")}</p>
                )}
              </section>
              <section className="border-t border-[#e3eaf8] pt-4">
                <h4 className="text-xs font-semibold text-[#171923]">{t("下一步重点核验", "Next checks")}</h4>
                {memo.open_questions?.length ? (
                  <ul className="mt-2 space-y-1 text-[11px] leading-relaxed text-[#505369]">
                    {memo.open_questions.map((x) => (
                      <li key={x}>☐ {clipBrief(x)}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-[11px] text-[#77718c]">{t("待补充", "TBD")}</p>
                )}
              </section>
            </div>

            <p className="mt-4 border-t border-[#e3eaf8] pt-3 text-[10px] text-[#77718c]">
              {t("AI 辅助研究，数据及结论仅供核对参考，不构成投资建议。", "AI-assisted research; data and conclusions are for verification only and are not investment advice.")}
            </p>
          </div>
        ) : (
          <Empty>
            {memoBusy
              ? t("AI 一页纸生成中…", "Generating AI one-pager…")
              : t("还没有 AI 一页纸，点击右上角生成。", "No AI one-pager yet; generate it from the top-right button.")}
          </Empty>
        )}
      </Card>

      {returnOpen && version ? (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#171923]/45 p-3 sm:p-6"
          role="presentation"
          onClick={() => {
            if (busy !== "return") setReturnOpen(false);
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="return-dialog-title"
            className="my-4 w-full max-w-lg rounded-2xl bg-white p-5 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 id="return-dialog-title" className="font-display text-lg font-semibold text-[#171923]">
              {t("退回并重跑", "Return & rerun")}
            </h2>
            <p className="mt-1 text-xs leading-relaxed text-[#68738b]">
              {t("勾选要重跑的板块/维度并填写原因；系统会保留其余内容，重跑后版本号 +1，旧版本作废。", "Select the sections or dimensions to rerun and give a reason; the rest is kept, the version increments, and the old version is voided.")}
            </p>
            <div className="mt-3 grid grid-cols-2 gap-1.5 text-xs">
              <label className="flex items-center gap-2 rounded-lg border border-[#dee5f2] px-2 py-1.5">
                <input
                  type="checkbox"
                  checked={returnTargets.includes("industry")}
                  onChange={(e) =>
                    setReturnTargets((prev) =>
                      e.target.checked ? [...new Set([...prev, "industry"])] : prev.filter((x) => x !== "industry"),
                    )
                  }
                />
                {t("行业分析", "Industry")}
              </label>
              {AGENT_TITLES.map(([key, label]) => (
                <label key={key} className="flex items-center gap-2 rounded-lg border border-[#dee5f2] px-2 py-1.5">
                  <input
                    type="checkbox"
                    checked={returnTargets.includes(key)}
                    onChange={(e) =>
                      setReturnTargets((prev) =>
                        e.target.checked ? [...new Set([...prev, key])] : prev.filter((x) => x !== key),
                      )
                    }
                  />
                  {label}
                </label>
              ))}
            </div>
            <label className="mt-3 block text-xs text-[#68738b]">
              {t("退回原因（必填）", "Return reason (required)")}
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                className="mt-1 min-h-[76px] w-full rounded-lg border border-[#dde5f2] bg-[#f8faff] p-2 text-xs outline-none focus:border-[#7950ba]"
                placeholder={t("例如：财务维度未验证现金流与利润勾稽；行业规模数据缺失。", "e.g. financial cash-flow cross-check missing; industry size data missing.")}
              />
            </label>
            {returnError ? (
              <p className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[11px] text-red-700">{returnError}</p>
            ) : null}
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <Button variant="ghost" disabled={busy === "return"} onClick={() => setReturnOpen(false)}>
                {t("取消", "Cancel")}
              </Button>
              <Button variant="danger" disabled={busy === "return"} onClick={() => void submitReturn()}>
                {busy === "return" ? t("重跑中…", "Rerunning…") : t("确认退回并重跑", "Return & rerun")}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {evidenceOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#171923]/45 p-3 sm:p-6"
          onClick={() => setEvidenceOpen(false)}
          role="presentation"
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="evidence-dialog-title"
            className="my-4 w-full max-w-4xl rounded-2xl bg-white shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="sticky top-0 z-10 flex flex-wrap items-start justify-between gap-3 rounded-t-2xl border-b border-[#e3eaf8] bg-white px-5 py-4">
              <div>
                <h2 id="evidence-dialog-title" className="font-display text-lg font-semibold text-[#171923]">
                  {t("证据与反证", "Evidence & counter-evidence")}
                </h2>
                <p className="mt-1 max-w-2xl text-xs leading-relaxed text-[#68738b]">
                  {t(
                    "每条结论引用的证据都在这里。先看类型和来源，再核对原文摘录；没有证据 ID 的结论不能进入审批包。",
                    "Every cited evidence item is here. Check its type and source first, then the quote; conclusions without evidence IDs cannot enter the approval package.",
                  )}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Badge tone="gold">
                  {detail.evidence?.length || 0} {t("条证据", "items")}
                </Badge>
                <Button variant="ghost" onClick={() => setEvidenceOpen(false)}>
                  {t("关闭", "Close")}
                </Button>
              </div>
            </div>
            <div className="px-5 py-4">
              <div className="mb-3 rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-3">
                <p className="text-xs font-semibold text-[#505369]">{t("证据类型说明", "Evidence types")}</p>
                <div className="mt-2 grid gap-1.5 text-[11px] text-[#68738b] sm:grid-cols-2">
                  {Object.entries(EVIDENCE_TYPE_META).map(([key, meta]) => (
                    <span key={key} className="flex items-start gap-2">
                      <Badge tone={meta.tone}>{meta.label}</Badge>
                      <span className="leading-relaxed">{meta.note}</span>
                    </span>
                  ))}
                </div>
              </div>
              <div className="mb-4 rounded-xl border border-[#e3eaf8] bg-[#f8faff] p-3">
                <p className="text-xs font-semibold text-[#505369]">{t("证据等级", "Evidence grades")}</p>
                <div className="mt-2 grid gap-1.5 text-[11px] text-[#68738b] sm:grid-cols-2">
                  {Object.entries(EVIDENCE_GRADE_META).map(([key, meta]) => (
                    <span key={key} className="flex items-start gap-2">
                      <Badge tone={meta.tone}>{meta.label}</Badge>
                      <span className="leading-relaxed">{meta.note}</span>
                    </span>
                  ))}
                </div>
              </div>
              {detail.evidence?.length ? (
                <ul className="space-y-3">
                  {detail.evidence.map((ev) => {
                    const meta = EVIDENCE_TYPE_META[ev.evidence_type || "fact"] || EVIDENCE_TYPE_META.fact;
                    const grade = EVIDENCE_GRADE_META[ev.grade || "D"] || EVIDENCE_GRADE_META.D;
                    return (
                      <li key={ev.id} className="rounded-xl border border-[#e3eaf8] bg-white p-4">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <p className="min-w-0 text-sm font-medium text-[#252533]">
                            <span className="mr-2 font-mono text-[10px] text-[#77718c]">#{ev.id}</span>
                            {ev.title}
                          </p>
                        </div>
                        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                          <Badge tone={grade.tone}>{grade.label}</Badge>
                          <Badge tone={meta.tone}>{meta.label}</Badge>
                          <Badge>{sourceLabel(ev.source)}</Badge>
                          <span className="text-[10px] text-[#77718c]">
                            {t("数据日期", "As of")}：{ev.as_of || t("待补充", "TBD")}
                          </span>
                          <span className="text-[10px] text-[#77718c]">
                            {t("可用时间", "Available")}：{ev.available_time || ev.as_of || t("待补充", "TBD")}
                          </span>
                          {ev.document_id || ev.page_ref ? (
                            <span className="text-[10px] text-[#77718c]">
                              {t("原文", "Source")}：{[ev.document_id, ev.page_ref].filter(Boolean).join(" / ")}
                            </span>
                          ) : null}
                        </div>
                        <blockquote className="mt-2 rounded-lg border-l-2 border-[#7950ba]/40 bg-[#f8faff] px-3 py-2 text-xs leading-relaxed text-[#505369]">
                          {ev.quote || t("原始摘录待补充，需回源核对。", "Quote pending; verify against the source.")}
                        </blockquote>
                        <p className="mt-1.5 text-[10px] leading-relaxed text-[#77718c]">{meta.note}</p>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <Empty>
                  {t(
                    "还没有证据。生成研究会写入行情、估值与财务证据。",
                    "No evidence yet; generating research writes price, valuation and financial evidence.",
                  )}
                </Empty>
              )}
            </div>
          </div>
        </div>
      ) : null}

      <p className="text-[11px] leading-relaxed text-[#77718c]">
        {t("研究结论由数据与规则生成，AI 仅提供解释与反证建议；估值口径为演示，不是目标价。数据不足时显示「待补充」，不构成投资建议。", "Conclusions come from data and rules; AI only explains and suggests falsifiers. Valuation is illustrative, not a target price. Missing data shows TBD. Not investment advice.")}
      </p>
    </div>
  );
}
