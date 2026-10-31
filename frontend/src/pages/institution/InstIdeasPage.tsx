import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Telescope } from "lucide-react";
import { instApi, fmtNum } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, Empty, ErrorBox, Loading, PageHeader, StatusBadge } from "./instUi";

type Company = {
  id: number;
  symbol: string;
  name: string;
  market: string;
  industry?: string;
  ref_price?: number;
  data_status?: string;
  pool_status?: string;
  tags?: string[];
  research_points?: string[];
  pending_items?: string[];
};

const PAGE_SIZE = 60;

export function InstIdeasPage() {
  const session = useInstSession();
  const { locale, market, t } = useInstLocale();
  const nav = useNavigate();
  const [items, setItems] = useState<Company[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canWrite = (session.permissions.ideas || "none") === "write";
  const scopeLabel =
    locale === "zh" ? "A 股全市场" : "US full market";
  const scopeNote =
    locale === "zh"
      ? "中文研究范围：A 股全市场"
      : "English research scope: US full market";

  const fetchPage = (nextOffset: number, append: boolean) => {
    if (append) setLoadingMore(true);
    else setLoading(true);
    setError(null);
    const params = new URLSearchParams({
      market,
      limit: String(PAGE_SIZE),
      offset: String(nextOffset),
    });
    if (q.trim()) params.set("q", q.trim());
    instApi<{ items: Company[]; total: number; limit: number; offset: number }>(
      `/companies?${params.toString()}`,
    )
      .then((data) => {
        const next = data.items || [];
        setItems((prev) => (append ? [...prev, ...next] : next));
        setTotal(data.total || 0);
        setOffset(nextOffset + next.length);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => {
        setLoading(false);
        setLoadingMore(false);
      });
  };

  useEffect(() => {
    fetchPage(0, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market]);

  const search = () => fetchPage(0, false);

  const enterResearch = async (company: Company) => {
    if (!canWrite) return;
    setBusy(company.id);
    setError(null);
    try {
      const res = await instApi<{ id: number }>("/cases", {
        method: "POST",
        body: { company_id: company.id },
      });
      nav(`/inst/research?case=${res.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const setPool = async (company: Company, pool_status: string) => {
    if (!canWrite) return;
    setBusy(company.id);
    setError(null);
    try {
      await instApi(`/companies/${company.id}/pool`, {
        method: "POST",
        body: {
          pool_status,
          reason: pool_status === "dropped" ? t("未入选：待补充研究理由", "Not selected: research rationale pending") : null,
        },
      });
      fetchPage(0, false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="DISCOVERY / 02"
        title={t("机会发现", "Discovery")}
        desc={t(
          "从行业、估值与经营变化中发现研究线索；立项、观察或放弃都要保留理由。",
          "Find research leads from industry, valuation and business changes; keep a reason for every decision.",
        )}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="gold">{scopeLabel}</Badge>
            <Badge>{total} {t("个对象", "names")}</Badge>
          </div>
        }
      />

      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") search();
              }}
              placeholder={t(
                "输入公司名、代码或行业，回车筛选",
                "Search company, ticker or sector; press Enter",
              )}
              className="w-full rounded-lg border border-[#dcd6c8] bg-[#faf9f5] py-2 pl-9 pr-3 text-sm outline-none focus:border-[#c9a15e]"
            />
          </div>
          <Button variant="gold" onClick={search}>
            {t("筛选", "Search")}
          </Button>
          <span className="text-[11px] text-slate-400">{scopeNote}</span>
        </div>
        {error ? <div className="mt-3"><ErrorBox message={error} onRetry={() => fetchPage(0, false)} /></div> : null}
      </Card>

      {loading ? <Loading label={t("正在加载研究对象…", "Loading research universe…")} /> : null}

      {!loading && !items.length ? (
        <Empty>
          <Telescope className="mx-auto mb-2 h-6 w-6 text-slate-300" />
          {t("没有匹配的研究对象。换一个关键词或恢复市场筛选。", "No matching names. Try another keyword.")}
        </Empty>
      ) : null}

      {!loading && items.length ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {items.map((c) => (
            <article key={c.id} className="flex flex-col rounded-2xl border border-[#e7e3d8] bg-white p-5">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="font-display text-base font-semibold text-slate-900">{c.name}</h3>
                  <p className="mt-0.5 font-mono text-[11px] text-slate-500">{c.symbol}</p>
                </div>
                <StatusBadge status={c.data_status} />
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <Badge tone="gold">{c.industry || t("行业待补充", "Sector TBD")}</Badge>
                <Badge>{c.market}</Badge>
                {c.pool_status === "watch" ? <Badge tone="amber">{t("观察池", "Watchlist")}</Badge> : null}
                {c.pool_status === "dropped" ? <Badge tone="red">{t("已放弃", "Dropped")}</Badge> : null}
              </div>
              <dl className="mt-3 space-y-1.5 text-xs text-slate-500">
                <div className="flex justify-between gap-2">
                  <dt>{t("参考价", "Reference price")}</dt>
                  <dd className="font-mono text-slate-800">{fmtNum(c.ref_price, 2)}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>{t("研究关注点", "Focus")}</dt>
                  <dd className="max-w-[70%] text-right text-slate-700">
                    {(c.research_points || [])[0] || t("待补充", "TBD")}
                  </dd>
                </div>
              </dl>
              <div className="mt-4 flex flex-wrap gap-2 border-t border-[#f0ece2] pt-3">
                <Button variant="primary" disabled={!canWrite || busy === c.id} onClick={() => enterResearch(c)}>
                  {busy === c.id ? t("处理中…", "Working…") : t("进入研究", "Start research")}
                </Button>
                <Button variant="ghost" disabled={!canWrite || busy === c.id} onClick={() => setPool(c, "watch")}>
                  {t("观察", "Watch")}
                </Button>
                <Button variant="ghost" disabled={!canWrite || busy === c.id} onClick={() => setPool(c, "dropped")}>
                  {t("放弃", "Drop")}
                </Button>
              </div>
            </article>
          ))}
        </div>
      ) : null}

      {!loading && items.length < total ? (
        <div className="flex justify-center">
          <Button variant="ghost" disabled={loadingMore} onClick={() => fetchPage(offset, true)}>
            {loadingMore ? t("加载中…", "Loading…") : t(`加载更多（${items.length}/${total}）`, `Load more (${items.length}/${total})`)}
          </Button>
        </div>
      ) : null}

      <p className="text-[11px] leading-relaxed text-slate-400">
        {t(
          "中文研究范围为 A 股全市场，英文研究范围为美股全市场；A 股研究使用真实公开行情与财务，美股当前只有行情，基本面标注“待补充”。机会发现结果不是投资建议。",
          "The Chinese scope is the full A-share market; the English scope is the full US market. A-shares use real public prices and financials; US currently has prices only, with fundamentals marked TBD. Discovery results are not investment advice.",
        )}
      </p>
    </div>
  );
}
