import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Disclaimer, ErrorState, PageHeader } from "../components";

const SECTIONS: Array<[string, string]> = [
  ["strategy", "策略分享"],
  ["factor", "因子笔记"],
  ["qa", "问答"],
  ["hotspot", "热点分析"],
];

export default function PostNew() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [section, setSection] = useState("strategy");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!user) {
    return (
      <div className="page">
        <PageHeader title="发帖" back onBack={() => nav(-1)} />
        <ErrorState message="请先登录后再发帖" onRetry={() => nav("/login")} />
      </div>
    );
  }

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const data = await api<{ id?: number }>("/api/community/posts", {
        method: "POST",
        body: JSON.stringify({ section, title: title.trim(), body: body.trim() }),
      });
      if (data?.id) nav(`/community/${data.id}`, { replace: true });
      else nav("/community", { replace: true });
    } catch (e: any) {
      setError(e.message || "发布失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader title="发帖" sub="遵守社区规范 · 不构成投资建议" back onBack={() => nav(-1)} />
      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}

      <div className="card">
        <div className="chips">
          {SECTIONS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={`chip ${section === value ? "on" : ""}`}
              onClick={() => setSection(value)}
            >
              {label}
            </button>
          ))}
        </div>

        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={80}
          placeholder="标题（2–80 字）"
          style={{ width: "100%", marginTop: 12, padding: 10, borderRadius: 10, border: "1px solid var(--line)", fontSize: 14 }}
        />
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          maxLength={8000}
          placeholder="正文：观点、依据与风险提示"
          style={{ width: "100%", minHeight: 220, marginTop: 10, padding: 10, borderRadius: 10, border: "1px solid var(--line)", fontSize: 14 }}
        />
        <button
          className="btn btn-primary w100"
          style={{ marginTop: 12 }}
          disabled={busy || title.trim().length < 2 || body.trim().length < 1}
          onClick={submit}
        >
          {busy ? "发布中…" : "发布"}
        </button>
      </div>

      <Disclaimer>请勿发布荐股、收益承诺或侵权内容；违规内容会被处理。</Disclaimer>
    </div>
  );
}
