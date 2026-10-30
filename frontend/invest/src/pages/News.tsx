import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { api } from "../api";
import { Disclaimer, ErrorState, LoadingCards, PageHeader, Tag } from "../components";

const TABS = [
  { key: "all", label: "全部" },
  { key: "news", label: "要闻" },
  { key: "announcement", label: "公告" },
  { key: "research", label: "研报" },
];

export default function News() {
  const [kind, setKind] = useState("all");
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    api(`/api/invest/news${kind === "all" ? "" : `?kind=${kind}`}`)
      .then(setData)
      .catch((e) => setError(e.message));
  };
  useEffect(load, [kind]);

  return (
    <div className="page">
      <PageHeader title="资讯" sub="标题 + 来源 + 链接 · 非投资建议" />
      <div className="seg news-seg">
        {TABS.map((t) => (
          <button key={t.key} className={kind === t.key ? "on" : ""} onClick={() => setKind(t.key)}>{t.label}</button>
        ))}
      </div>

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!data && !error ? <LoadingCards rows={4} /> : null}

      {data ? (
        <div className="news-list card">
          {data.items.length === 0 ? <div className="empty-inline">暂无资讯。</div> : data.items.map((n: any) => (
            <a className="news-item" key={n.id} href={n.url} target="_blank" rel="noreferrer">
              <div className="news-item-top">
                <Tag tone={n.kind === "announcement" ? "blue" : n.kind === "research" ? "amber" : "gray"}>
                  {n.kind === "announcement" ? "公告" : n.kind === "research" ? "研报" : "要闻"}
                </Tag>
                <span>{n.source} · {n.published_at}</span>
              </div>
              <b>{n.title}</b>
              <p>{n.summary}</p>
              <em className="news-link">查看原文 <ExternalLink size={12} /></em>
            </a>
          ))}
        </div>
      ) : null}

      <Disclaimer>{data?.isDemo ? "资讯为演示标题；公开版需接真实源并核对版权。" : "公告/研报/要闻均为公开标题+链接。非投资建议；转载/商用前需核对版权。"}</Disclaimer>
    </div>
  );
}
