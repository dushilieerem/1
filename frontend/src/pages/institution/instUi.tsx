import type { ReactNode } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

export function PageHeader({
  eyebrow,
  title,
  desc,
  actions,
}: {
  eyebrow?: string;
  title: string;
  desc?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-[#e7e3d8] bg-white px-6 py-6">
      <div>
        {eyebrow ? (
          <p className="text-[11px] tracking-[0.18em] text-[#8a6a2f]">{eyebrow}</p>
        ) : null}
        <h1 className="mt-1 font-display text-2xl font-semibold text-slate-900">{title}</h1>
        {desc ? <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">{desc}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function Card({
  title,
  desc,
  actions,
  children,
  className = "",
}: {
  title?: string;
  desc?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-2xl border border-[#e7e3d8] bg-white p-5 ${className}`}>
      {title || actions ? (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
          <div>
            {title ? <h2 className="font-display text-lg font-semibold text-slate-900">{title}</h2> : null}
            {desc ? <p className="mt-1 text-xs leading-relaxed text-slate-500">{desc}</p> : null}
          </div>
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  type = "button",
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "ghost" | "danger" | "gold";
  type?: "button" | "submit";
  title?: string;
}) {
  const styles: Record<string, string> = {
    primary: "bg-[#0b1220] text-white hover:bg-[#16233a]",
    gold: "bg-[#c9a15e] text-[#1b2436] hover:bg-[#d8b476]",
    ghost: "border border-[#dcd6c8] bg-white text-slate-700 hover:bg-[#faf8f2]",
    danger: "border border-[#d9a3a3] bg-[#fff5f5] text-[#9b2c2c] hover:bg-[#fdecec]",
  };
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center rounded-lg px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles[variant]}`}
    >
      {children}
    </button>
  );
}

export function Badge({
  children,
  tone = "slate",
}: {
  children: ReactNode;
  tone?: "slate" | "gold" | "green" | "red" | "amber" | "blue";
}) {
  const map: Record<string, string> = {
    slate: "border-slate-200 bg-slate-50 text-slate-600",
    gold: "border-[#c9a15e]/40 bg-[#fbf6ea] text-[#8a6a2f]",
    green: "border-emerald-200 bg-emerald-50 text-emerald-700",
    red: "border-red-200 bg-red-50 text-red-700",
    amber: "border-amber-200 bg-amber-50 text-amber-700",
    blue: "border-sky-200 bg-sky-50 text-sky-700",
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${map[tone]}`}>
      {children}
    </span>
  );
}

export function Loading({ label = "加载中…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 rounded-2xl border border-[#e7e3d8] bg-white py-16 text-sm text-slate-500">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <div className="flex-1">
          <p>{message}</p>
          {onRetry ? (
            <button type="button" onClick={onRetry} className="mt-2 underline">
              重试
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-[#dcd6c8] bg-[#faf9f5] px-4 py-10 text-center text-sm text-slate-500">
      {children}
    </div>
  );
}

export function StatusBadge({ status }: { status?: string | null }) {
  const map: Record<string, { label: string; tone: "slate" | "gold" | "green" | "red" | "amber" | "blue" }> = {
    draft: { label: "草稿", tone: "slate" },
    planning: { label: "计划中", tone: "slate" },
    researching: { label: "研究中", tone: "blue" },
    pending_review: { label: "待研究审核", tone: "amber" },
    package_ready: { label: "资料包就绪", tone: "blue" },
    approved: { label: "研究已通过", tone: "green" },
    debate: { label: "辩论中", tone: "blue" },
    proposal: { label: "已进入议案", tone: "gold" },
    closed: { label: "已关闭", tone: "slate" },
    partner_review: { label: "待合伙人复核", tone: "amber" },
    chairman_review: { label: "待 Chairman 审批", tone: "amber" },
    risk_precheck: { label: "待执行前风控", tone: "amber" },
    authorized: { label: "已授权", tone: "green" },
    executed: { label: "已执行", tone: "green" },
    rejected: { label: "已拒绝", tone: "red" },
    frozen: { label: "风控冻结", tone: "red" },
    pending: { label: "待开始", tone: "slate" },
    running: { label: "运行中", tone: "blue" },
    completed: { label: "已完成", tone: "green" },
    failed: { label: "失败", tone: "red" },
    done: { label: "已完成", tone: "green" },
    partial: { label: "待补充", tone: "amber" },
    missing: { label: "无数据", tone: "red" },
    real: { label: "真实数据", tone: "green" },
    pass: { label: "通过", tone: "green" },
    block: { label: "阻断", tone: "red" },
    veto: { label: "否决", tone: "red" },
    qualified: { label: "有效授权", tone: "green" },
    filled: { label: "已成交", tone: "green" },
  };
  const item = map[status || ""] || { label: status || "—", tone: "slate" as const };
  return <Badge tone={item.tone}>{item.label}</Badge>;
}

export function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-[#f0ece2] py-2.5 text-sm last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className="text-right font-medium text-slate-900">{value}</span>
    </div>
  );
}
