import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Disclaimer, ErrorState, PageHeader } from "../components";
import { useLocale } from "../i18n";

const SECTIONS: Array<{ value: string; zh: string; en: string }> = [
  { value: "strategy", zh: "策略分享", en: "Strategy sharing" },
  { value: "factor", zh: "因子笔记", en: "Factor notes" },
  { value: "qa", zh: "问答", en: "Q&A" },
  { value: "hotspot", zh: "热点分析", en: "Hot topic analysis" },
];

export default function PostNew() {
  const nav = useNavigate();
  const { user } = useAuth();
  const { t } = useLocale();
  const [section, setSection] = useState("strategy");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!user) {
    return (
      <div className="page">
        <PageHeader title={t("发帖", "New post")} back onBack={() => nav(-1)} />
        <ErrorState message={t("请先登录后再发帖", "Please log in before posting")} onRetry={() => nav("/login")} />
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
      setError(e.message || t("发布失败", "Publish failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader title={t("发帖", "New post")} sub={t("遵守社区规范 · 不构成投资建议", "Follow community guidelines · not investment advice")} back onBack={() => nav(-1)} />
      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}

      <div className="card">
        <div className="chips">
          {SECTIONS.map((item) => (
            <button
              key={item.value}
              type="button"
              className={`chip ${section === item.value ? "on" : ""}`}
              onClick={() => setSection(item.value)}
            >
              {t(item.zh, item.en)}
            </button>
          ))}
        </div>

        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={80}
          placeholder={t("标题（2–80 字）", "Title (2–80 characters)")}
          style={{ width: "100%", marginTop: 12, padding: 10, borderRadius: 10, border: "1px solid var(--line)", fontSize: 14 }}
        />
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          maxLength={8000}
          placeholder={t("正文：观点、依据与风险提示", "Body: your view, rationale, and risk notes")}
          style={{ width: "100%", minHeight: 220, marginTop: 10, padding: 10, borderRadius: 10, border: "1px solid var(--line)", fontSize: 14 }}
        />
        <button
          className="btn btn-primary w100"
          style={{ marginTop: 12 }}
          disabled={busy || title.trim().length < 2 || body.trim().length < 1}
          onClick={submit}
        >
          {busy ? t("发布中…", "Publishing…") : t("发布", "Publish")}
        </button>
      </div>

      <Disclaimer>{t("请勿发布荐股、收益承诺或侵权内容；违规内容会被处理。", "Do not post stock recommendations, return promises, or infringing content; violations will be handled.")}</Disclaimer>
    </div>
  );
}
