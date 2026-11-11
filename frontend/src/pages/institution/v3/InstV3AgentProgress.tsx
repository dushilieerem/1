import { useEffect, useState } from "react";

export type AgentProgressStep = {
  key?: string;
  label: string;
  status?: string;
};

type Props = {
  active: boolean;
  title: string;
  detail?: string;
  steps?: AgentProgressStep[];
};

function fmt(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

const DONE = new Set(["done", "needs_review", "success"]);

export default function InstV3AgentProgress({ active, title, detail, steps }: Props) {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (!active) {
      setSeconds(0);
      return;
    }
    const started = Date.now();
    setSeconds(0);
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [active, title]);

  if (!active) return null;
  const done = (steps || []).filter((s) => DONE.has(String(s.status || ""))).length;

  return (
    <div className="v3-ai-progress" role="status" aria-live="polite">
      <span className="v3-spinner" aria-hidden="true" />
      <div className="v3-ai-progress-body">
        <div className="v3-ai-progress-title">
          <b>{title}</b>
          <span>已用时 {fmt(seconds)}</span>
        </div>
        {detail ? <div className="v3-ai-progress-detail">{detail}</div> : null}
        {steps?.length ? (
          <div className="v3-ai-steps">
            {steps.map((s) => (
              <span key={s.key || s.label} className={`v3-ai-step ${DONE.has(String(s.status || "")) ? "done" : s.status === "running" ? "running" : ""}`}>
                <i aria-hidden="true" />
                {s.label}
              </span>
            ))}
            <span className="v3-ai-step-count">已完成 {done}/{steps.length}</span>
          </div>
        ) : null}
        {seconds >= 45 ? (
          <div className="v3-ai-progress-hint">AI 仍在生成，长报告通常需要 1–3 分钟，请勿关闭页面。</div>
        ) : null}
      </div>
    </div>
  );
}
