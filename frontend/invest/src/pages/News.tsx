import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { api } from "../api";
import { Disclaimer, ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { useLocale, withMarket } from "../i18n";

const TABS = [
  { key: "all", zh: "全部", en: "All" },
  { key: "news", zh: "要闻", en: "Headlines" },
  { key: "announcement", zh: "公告", en: "Filings" },
  { key: "research", zh: "研报", en: "Research" },
];

export default function News() {
  const { t, market } = useLocale();
  const [kind, setKind] = useState("all");
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    api(withMarket(`/api/invest/news${kind === "all" ? "" : `?kind=${kind}`}`, market))
      .then(setData)
      .catch((e) => setError(e.message));
  };
  useEffect(load, [kind, market]);

  return (
    <div className="page">
      <PageHeader title={t("资讯", "News")} sub={t("标题 + 来源 + 链接 · 非投资建议", "Headline + source + link · not investment advice")} />
      {market === "CN" ? (
        <div className="seg news-seg">
          {TABS.map((item) => (
            <button key={item.key} className={kind === item.key ? "on" : ""} onClick={() => setKind(item.key)}>{t(item.zh, item.en)}</button>
          ))}
        </div>
      ) : null}

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!data && !error ? <LoadingCards rows={4} /> : null}

      {data ? (
        <div className="news-list card">
          {data.items.length === 0 ? <div className="empty-inline">{market === "US" ? t("美股资讯暂未接入；当前只提供行情与自选。", "US news is not connected yet; this build covers quotes and watchlists only.") : t("暂无资讯。", "No news yet.")}</div> : data.items.map((n: any) => (
            <a className="news-item" key={n.id} href={n.url} target="_blank" rel="noreferrer">
              <div className="news-item-top">
                <Tag tone={n.kind === "announcement" ? "blue" : n.kind === "research" ? "amber" : "gray"}>
                  {n.kind === "announcement" ? t("公告", "Filing") : n.kind === "research" ? t("研报", "Research") : t("要闻", "Headline")}
                </Tag>
                <span>{n.source} · {n.published_at}</span>
              </div>
              <b>{n.title}</b>
              <p>{n.summary}</p>
              <em className="news-link">{t("查看原文", "Open source")} <ExternalLink size={12} /></em>
            </a>
          ))}
        </div>
      ) : null}

      <Disclaimer>{market === "US" ? t("美股资讯暂未接入 · 非投资建议", "US news not connected yet · not investment advice") : data?.isDemo ? t("资讯为演示标题；公开版需接真实源并核对版权。", "News items are demo headlines; the public build needs real sources and copyright checks.") : t("公告/研报/要闻均为公开标题+链接。非投资建议；转载/商用前需核对版权。", "Filings, research and headlines are public titles + links. Not investment advice; verify copyright before redistribution.")}</Disclaimer>
    </div>
  );
}
