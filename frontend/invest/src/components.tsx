import { useEffect, useRef, type ReactNode } from "react";
import { AlertTriangle, ChevronLeft, RefreshCw, X } from "lucide-react";

export function Tag({ children, tone = "gray" }: { children: ReactNode; tone?: "red" | "green" | "amber" | "orange" | "gray" | "blue" }) {
  return <span className={`tag tag-${tone}`}>{children}</span>;
}

export function PageHeader({
  title,
  sub,
  right,
  back,
  onBack,
}: {
  title: string;
  sub?: string;
  right?: ReactNode;
  back?: boolean;
  onBack?: () => void;
}) {
  return (
    <header className="page-head">
      {back ? (
        <button className="round-btn" onClick={onBack} aria-label="返回">
          <ChevronLeft size={22} />
        </button>
      ) : null}
      <div className="page-head-text">
        <h1>{title}</h1>
        {sub ? <p>{sub}</p> : null}
      </div>
      {right ? <div className="page-head-right">{right}</div> : null}
    </header>
  );
}

export function SectionHead({ title, sub, action }: { title: string; sub?: string; action?: ReactNode }) {
  return (
    <div className="section-head">
      <div>
        <h2>{title}</h2>
        {sub ? <p>{sub}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function Sheet({
  open,
  onClose,
  title,
  sub,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  sub?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const sheetRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    const prevFocus = document.activeElement as HTMLElement | null;
    document.body.style.overflow = "hidden";
    const node = sheetRef.current;
    const selector = 'button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])';
    const focusables = () => Array.from(node?.querySelectorAll<HTMLElement>(selector) || [])
      .filter((el) => !el.hasAttribute("disabled") && el.offsetParent !== null);
    (focusables()[0] || node)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const list = focusables();
      if (!list.length) {
        e.preventDefault();
        node?.focus();
        return;
      }
      const first = list[0];
      const last = list[list.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
      prevFocus?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="sheet-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={sheetRef}>
        <div className="sheet-head">
          <div>
            <h3>{title}</h3>
            {sub ? <p>{sub}</p> : null}
          </div>
          <button className="round-btn" onClick={onClose} aria-label="关闭">
            <X size={18} />
          </button>
        </div>
        <div className="sheet-body">{children}</div>
        {footer ? <div className="sheet-footer">{footer}</div> : null}
      </div>
    </div>
  );
}

export function LoadingCards({ rows = 3 }: { rows?: number }) {
  return (
    <div className="stack">
      {Array.from({ length: rows }).map((_, i) => (
        <div className="skeleton-card" key={i}>
          <div className="skeleton sk-line w40" />
          <div className="skeleton sk-line w90" />
          <div className="skeleton sk-line w70" />
        </div>
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state-box">
      <AlertTriangle size={26} />
      <b>加载失败</b>
      <p>{message}</p>
      {onRetry ? (
        <button className="btn btn-ghost" onClick={onRetry}>
          <RefreshCw size={16} /> 重试
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({ title, detail, action }: { title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="state-box">
      <div className="empty-dot" />
      <b>{title}</b>
      {detail ? <p>{detail}</p> : null}
      {action}
    </div>
  );
}

export function Sparkline({ values, width = 96, height = 34 }: { values: number[]; width?: number; height?: number }) {
  if (!values || values.length < 2) return <div className="spark-empty" style={{ width, height }} />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values
    .map((v, i) => `${(i / (values.length - 1)) * width},${height - 4 - ((v - min) / span) * (height - 8)}`)
    .join(" ");
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="spark" aria-hidden="true">
      <polyline points={points} fill="none" stroke="var(--red)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function RiskRing({ score, size = 92, color }: { score: number; size?: number; color?: string }) {
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div
      className="risk-ring"
      style={{
        width: size,
        height: size,
        background: `conic-gradient(${color || "var(--red)"} ${pct * 3.6}deg, #f0f0f0 0deg)`,
      }}
    >
      <div className="risk-ring-in">
        <b>{score}</b>
        <span>风险分</span>
      </div>
    </div>
  );
}

export function BarRow({ label, value, width, suffix = "%" }: { label: string; value: number; width: number; suffix?: string }) {
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <div className="bar">
        <i style={{ width: `${Math.max(2, Math.min(100, width))}%` }} />
      </div>
      <span className="bar-value">
        {value.toFixed(1)}
        {suffix}
      </span>
    </div>
  );
}

export function Kv({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="kv">
      <span>{k}</span>
      <b>{v}</b>
    </div>
  );
}

export function Disclaimer({ children }: { children?: ReactNode }) {
  return <div className="disclaimer">{children || "收盘数据 · 非实时 · 不构成投资建议"}</div>;
}
