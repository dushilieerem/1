import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { useLocale } from "../i18n";

export default function Topics() {
  const nav = useNavigate();
  const { t, locale } = useLocale();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api("/api/invest/topics").then(setData).catch((e) => setError(e.message));
  }, []);
  return (
    <div className="page">
      <PageHeader title={t("今日热点", "Today's themes")} sub={t("按热度排序 · 每条带风险标签", "Ranked by heat · every row carries a risk flag")} back onBack={() => nav(-1)} />
      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {!data && !error ? <LoadingCards rows={3} /> : null}
      {data && !data.items?.length ? <EmptyState title={t("暂无热点", "No themes yet")} detail={t("数据更新后会在这里展示。", "Themes will appear after the data update.")} /> : null}
      {data?.items?.length ? (
        <div className="hot-list budget-list">
          {data.items.map((topic: any) => {
            const fallbackValue = topic.valuationPercentile ?? topic.turnoverPercentile;
            const tags = topic.riskTags?.length
              ? topic.riskTags
              : [{
                  label: fallbackValue != null ? `估值分位 ${Number(fallbackValue).toFixed(0)}%` : `热度 ${Number(topic.heat || 0).toFixed(0)}`,
                  label_en: fallbackValue != null ? `Valuation percentile ${Number(fallbackValue).toFixed(0)}%` : `Heat ${Number(topic.heat || 0).toFixed(0)}`,
                  tone: "gray",
                }];
            const body = (
              <>
                <div className="hot-top">
                  <b>{topic.name}</b>
                  <span className="hot-heat">{t("热度", "Heat")} {Number(topic.heat || 0).toFixed(0)}</span>
                </div>
                <p>{topic.summary}</p>
                <div className="hot-tags">
                  {tags.map((tag: any) => (
                    <Tag key={tag.label} tone={tag.tone || "gray"}>{locale === "en" ? tag.label_en || tag.label : tag.label}</Tag>
                  ))}
                  {topic.detailAvailable ? <span className="hot-list-go">{t("详情", "Details")} <ChevronRight size={13} /></span> : null}
                </div>
              </>
            );
            return topic.detailAvailable ? (
              <button className="hot-row list-hot-row" key={topic.id} onClick={() => nav(`/topic/${topic.id}`)}>{body}</button>
            ) : (
              <div className="hot-row list-hot-row hot-row-static" key={topic.id}>{body}</div>
            );
          })}
        </div>
      ) : null}
      {data?.disclaimer ? <p className="hint">{data.disclaimer}</p> : null}
    </div>
  );
}
