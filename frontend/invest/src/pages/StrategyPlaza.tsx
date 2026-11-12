import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bookmark, Eye, Users } from "lucide-react";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Sheet, Sparkline, Tag } from "../components";
import { useLocale } from "../i18n";

type Translate = (zh: string, en: string) => string;

type PlazaItem = {
  id: number;
  title: string;
  body: string;
  snapshot?: any;
  view_count?: number;
  created_at?: string;
  author?: { display_name?: string; username?: string };
};

const SORTS: Array<{ key: string; zh: string; en: string }> = [
  { key: "annual", zh: "收益榜", en: "Top return" },
  { key: "mdd", zh: "回撤榜", en: "Drawdown ranking" },
  { key: "views", zh: "关注榜", en: "Most viewed" },
];

function pct(value: any, t: Translate): string {
  const n = Number(value);
  return Number.isFinite(n) ? `${n.toFixed(1)}%` : "—";
}

function curveValues(item: PlazaItem): number[] {
  const curve = item.snapshot?.equity_curve ?? item.snapshot?.equity ?? [];
  if (Array.isArray(curve)) {
    return curve
      .map((x: any) => (typeof x === "number" ? x : Number(x?.equity ?? x?.value ?? x?.nav ?? x?.close)))
      .filter((x) => Number.isFinite(x));
  }
  return [];
}

export default function StrategyPlaza() {
  const nav = useNavigate();
  const { t } = useLocale();
  const [sort, setSort] = useState("annual");
  const [items, setItems] = useState<PlazaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<PlazaItem | null>(null);
  const [favs, setFavs] = useState<number[]>(() => {
    try {
      return JSON.parse(localStorage.getItem("svq_plaza_favs") || "[]");
    } catch {
      return [];
    }
  });

  useEffect(() => {
    setLoading(true);
    api<{ items: PlazaItem[] }>(`/api/strategy/plaza?sort=${sort}&limit=30`)
      .then((d) => setItems(d.items || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [sort]);

  const sortLabel = useMemo(() => {
    const current = SORTS.find((x) => x.key === sort);
    return current ? t(current.zh, current.en) : t("收益榜", "Top return");
  }, [sort, t]);

  const open = async (item: PlazaItem) => {
    try {
      const d = await api<{ item: PlazaItem }>(`/api/strategy/plaza/${item.id}?bump=0`);
      setActive(d.item);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const toggleFav = (id: number) => {
    const next = favs.includes(id) ? favs.filter((x) => x !== id) : [...favs, id];
    setFavs(next);
    try {
      localStorage.setItem("svq_plaza_favs", JSON.stringify(next));
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="page">
      <PageHeader
        title={t("策略广场", "Strategy Plaza")}
        sub={t("社区公开策略快照 · 历史收益不代表未来", "Community strategy snapshots · past returns do not guarantee future results")}
        back
        onBack={() => nav(-1)}
      />
      <div className="seg">
        {SORTS.map(({ key, zh, en }) => (
          <button key={key} className={sort === key ? "on" : ""} onClick={() => setSort(key)}>{t(zh, en)}</button>
        ))}
      </div>
      <p className="hint">
        {t(
          `当前排序：${sortLabel}；收益/回撤口径来自作者回测快照，未做跨策略统一。`,
          `Current sort: ${sortLabel}; return/drawdown figures come from the author's backtest snapshot and are not normalized across strategies.`,
        )}
      </p>
      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}
      {!loading && !items.length ? (
        <EmptyState
          title={t("策略广场暂无公开策略", "No public strategies yet")}
          detail={t("网页端发布策略快照后会出现在这里。", "They will appear here after a strategy snapshot is published on the web.")}
        />
      ) : null}
      <div className="post-list">
        {items.map((item) => {
          const m = item.snapshot?.metrics || {};
          const curve = curveValues(item);
          return (
            <div key={item.id} className="post-row">
              <button type="button" onClick={() => void open(item)} style={{ textAlign: "left", background: "none", border: 0, padding: 0 }}>
                <div className="post-row-title">{item.title}</div>
                <div className="post-row-meta">
                  <Tag tone="gray">{item.author?.display_name || item.author?.username || t("社区", "Community")}</Tag>
                  <span className="row gap6"><Eye size={12} /> {item.view_count ?? 0}</span>
                </div>
                <div className="hint">
                  {t("年化", "Annualized")} {pct(m.annual_return, t)} · {t("最大回撤", "Max drawdown")} {pct(m.max_drawdown, t)} · {t("夏普", "Sharpe")} {Number(m.sharpe || 0).toFixed(2)}
                </div>
                {curve.length ? <Sparkline values={curve} width={220} height={38} /> : null}
              </button>
              <button className={`link-btn ${favs.includes(item.id) ? "on" : ""}`} onClick={() => toggleFav(item.id)}>
                <Bookmark size={13} /> {favs.includes(item.id) ? t("已收藏", "Saved") : t("收藏", "Save")}
              </button>
            </div>
          );
        })}
      </div>
      <p className="hint">
        {t(
          "不展示他人源码与参数；收益口径以作者快照为准；非投资建议。",
          "Other users' source code and parameters are not shown; figures follow the author's snapshot; not investment advice.",
        )}
      </p>

      <Sheet open={!!active} onClose={() => setActive(null)} title={active?.title || t("策略详情", "Strategy details")} sub={t("公开快照 · 非投资建议", "Public snapshot · not investment advice")}>
        {active ? (
          <div>
            <p className="hint">
              <Users size={13} /> {active.author?.display_name || active.author?.username || t("社区作者", "Community author")} · {t("浏览", "views")} {active.view_count ?? 0}
            </p>
            <div className="kpi-grid">
              <div className="kpi"><span>{t("年化", "Annualized")}</span><b>{pct(active.snapshot?.metrics?.annual_return, t)}</b></div>
              <div className="kpi"><span>{t("最大回撤", "Max drawdown")}</span><b>{pct(active.snapshot?.metrics?.max_drawdown, t)}</b></div>
              <div className="kpi"><span>{t("夏普", "Sharpe")}</span><b>{Number(active.snapshot?.metrics?.sharpe || 0).toFixed(2)}</b></div>
            </div>
            <p className="muted small" style={{ whiteSpace: "pre-wrap" }}>{active.body || t("作者未填写说明。", "The author did not provide a description.")}</p>
            <p className="hint">
              {t(
                "不展示源码与参数；历史收益不代表未来，非投资建议。",
                "Source code and parameters are not shown; past returns do not guarantee future results; not investment advice.",
              )}
            </p>
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}
