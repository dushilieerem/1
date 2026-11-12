import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { api } from "../api";
import { Disclaimer, ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { useLocale, withMarket } from "../i18n";

export default function News() {
  const { t, market } = useLocale();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    api(withMarket("/api/invest/news", market))
      .then(setData)
      .catch((e) => setError(e.message));
  };
  useEffect(load, [market]);

  return (
    <div className="page">
      <PageHeader title={t("资讯", "News")} sub={t("要闻 · 标题 + 来源 + 链接 · 非投资建议", "Headlines · title + source + link · not investment advice")} />

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!data && !error ? <LoadingCards rows={4} /> : null}

      {data ? (
        <div className="news-list card">
          {data.items.length === 0 ? <div className="empty-inline">{market === "US" ? t("美股资讯暂未接入；当前只提供行情与自选。", "US news is not available (no free stable source); this build covers quotes and watchlists only.") : t("当前数据视图暂无资讯；缺失时不会用演示内容填充。", "No news in the current data view; missing items are not filled with demo content.")}</div> : data.items.map((n: any) => (
            <a className="news-item" key={n.id} href={n.url} target="_blank" rel="noreferrer">
              <div className="news-item-top">
                <Tag tone="gray">{t("要闻", "Headline")}</Tag>
                <span>{n.source} · {n.published_at}</span>
              </div>
              <b>{n.title}</b>
              <p>{n.summary}</p>
              <em className="news-link">{t("查看原文", "Open source")} <ExternalLink size={12} /></em>
            </a>
          ))}
        </div>
      ) : null}

      <Disclaimer>{market === "US" ? t("美股资讯暂未接入 · 非投资建议", "US news unavailable · not investment advice") : data?.isDemo ? t("资讯为演示标题；公开版需接真实源并核对版权。", "News items are demo headlines; the public build needs real sources and copyright checks.") : t("要闻为公开标题+链接。非投资建议；转载/商用前需核对版权。", "Headlines are public titles + links. Not investment advice; verify copyright before redistribution.")}</Disclaimer>
    </div>
  );
}
