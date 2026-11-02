import type { ReactNode } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { useInstLocale } from "@/components/institution/instLocale";

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
    <div className="flex flex-wrap items-start justify-between gap-4 px-0 py-1">
      <div>
        {eyebrow ? (
          <p className="text-[11px] tracking-[0.18em] text-[#b42345]">{eyebrow}</p>
        ) : null}
        <h1 className="mt-1 font-display text-[29px] font-semibold leading-tight tracking-[-0.03em] text-[#171923]">{title}</h1>
        {desc ? <p className="mt-2 max-w-3xl text-[13px] leading-relaxed text-[#68738b]">{desc}</p> : null}
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
    <section className={`rounded-xl border border-[#dde5f2] bg-white p-5 ${className}`}>
      {title || actions ? (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
          <div>
            {title ? <h2 className="font-display text-lg font-semibold text-[#171923]">{title}</h2> : null}
            {desc ? <p className="mt-1 text-xs leading-relaxed text-[#68738b]">{desc}</p> : null}
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
    primary: "bg-[#b42345] text-white hover:bg-[#a31f42]",
    gold: "bg-[#7950ba] text-white hover:bg-[#8a63c9]",
    ghost: "border border-[#dde5f2] bg-white text-[#505369] hover:bg-[#f5f0ff]",
    danger: "border border-[#e6b7c4] bg-[#fff0f4] text-[#9a2a48] hover:bg-[#fbe8ef]",
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
    slate: "border-[#dde5f2] bg-[#f3f6fd] text-[#68738b]",
    gold: "border-[#7950ba]/40 bg-[#f2eafa] text-[#7950ba]",
    green: "border-[#cfe3d8] bg-[#eef8f1] text-[#2f6b4f]",
    red: "border-[#e6b7c4] bg-[#fff0f4] text-[#9a2a48]",
    amber: "border-[#eadfbe] bg-[#fdf8ea] text-[#8a6a2f]",
    blue: "border-[#c9d8f5] bg-[#eef3ff] text-[#3b5f9e]",
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${map[tone]}`}>
      {children}
    </span>
  );
}

export function Loading({ label = "加载中…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 rounded-xl border border-[#dde5f2] bg-white py-16 text-sm text-[#68738b]">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
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
    <div className="rounded-xl border border-dashed border-[#dde5f2] bg-[#f8faff] px-4 py-10 text-center text-sm text-[#68738b]">
      {children}
    </div>
  );
}

export function StatusBadge({ status }: { status?: string | null }) {
  const { locale } = useInstLocale();
  const map: Record<string, { zh: string; en: string; tone: "slate" | "gold" | "green" | "red" | "amber" | "blue" }> = {
    draft: { zh: "草稿", en: "Draft", tone: "slate" },
    planning: { zh: "计划中", en: "Planning", tone: "slate" },
    researching: { zh: "研究中", en: "Researching", tone: "blue" },
    pending_review: { zh: "待研究审核", en: "Pending research review", tone: "amber" },
    package_ready: { zh: "资料包就绪", en: "Package ready", tone: "blue" },
    approved: { zh: "研究已通过", en: "Research approved", tone: "green" },
    debate: { zh: "辩论中", en: "Debating", tone: "blue" },
    proposal: { zh: "已进入议案", en: "Proposal stage", tone: "gold" },
    closed: { zh: "已关闭", en: "Closed", tone: "slate" },
    partner_review: { zh: "待合伙人复核", en: "Partner review", tone: "amber" },
    chairman_review: { zh: "待 Chairman 审批", en: "Chairman review", tone: "amber" },
    risk_precheck: { zh: "待执行前风控", en: "Pre-execution risk check", tone: "amber" },
    authorized: { zh: "已授权", en: "Authorized", tone: "green" },
    executed: { zh: "已执行", en: "Executed", tone: "green" },
    rejected: { zh: "已拒绝", en: "Rejected", tone: "red" },
    frozen: { zh: "风控冻结", en: "Risk frozen", tone: "red" },
    pending: { zh: "待开始", en: "Pending", tone: "slate" },
    running: { zh: "运行中", en: "Running", tone: "blue" },
    completed: { zh: "已完成", en: "Completed", tone: "green" },
    failed: { zh: "失败", en: "Failed", tone: "red" },
    done: { zh: "已完成", en: "Done", tone: "green" },
    partial: { zh: "待补充", en: "Partial", tone: "amber" },
    needs_review: { zh: "待复核", en: "Needs review", tone: "amber" },
    missing: { zh: "无数据", en: "No data", tone: "red" },
    real: { zh: "真实数据", en: "Real data", tone: "green" },
    pass: { zh: "通过", en: "Pass", tone: "green" },
    block: { zh: "阻断", en: "Blocked", tone: "red" },
    veto: { zh: "否决", en: "Vetoed", tone: "red" },
    qualified: { zh: "有效授权", en: "Qualified", tone: "green" },
    filled: { zh: "已成交", en: "Filled", tone: "green" },
  };
  const item = map[status || ""] || { zh: status || "—", en: status || "—", tone: "slate" as const };
  return <Badge tone={item.tone}>{locale === "en" ? item.en : item.zh}</Badge>;
}

export function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-[#e3eaf8] py-2.5 text-sm last:border-0">
      <span className="text-[#68738b]">{label}</span>
      <span className="text-right font-medium text-[#171923]">{value}</span>
    </div>
  );
}
