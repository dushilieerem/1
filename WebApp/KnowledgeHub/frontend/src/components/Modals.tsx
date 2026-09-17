import { useEffect, useRef } from "react";

/** 居中自定义弹层，避免浏览器原生 prompt/confirm 带站点标题 */
export function ModalShell({
  title,
  children,
  onClose,
  wide = false,
  /** 点遮罩是否关闭；长表单建议 false，避免误触丢内容 */
  closeOnBackdrop = true,
  /** Esc 是否关闭；长表单建议 false */
  closeOnEscape = true,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  /** 结构化填报等长表单用更宽弹层 */
  wide?: boolean;
  closeOnBackdrop?: boolean;
  closeOnEscape?: boolean;
}) {
  useEffect(() => {
    if (!closeOnEscape) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, closeOnEscape]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={closeOnBackdrop ? onClose : undefined}
      role="presentation"
    >
      <div
        className={`w-full rounded-2xl bg-white p-5 shadow-xl ${
          wide ? "max-w-[min(72rem,66vw)]" : "max-w-md"
        }`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          <button
            type="button"
            className="rounded px-2 text-lg leading-none text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            onClick={onClose}
            aria-label="关闭"
          >
            ×
          </button>
        </div>
        <div className="mt-4">{children}</div>
      </div>
    </div>
  );
}

export function NamePromptModal({
  title,
  label,
  defaultValue = "",
  placeholder,
  confirmText = "确定",
  onCancel,
  onConfirm,
}: {
  title: string;
  label: string;
  defaultValue?: string;
  placeholder?: string;
  confirmText?: string;
  onCancel: () => void;
  onConfirm: (value: string) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    ref.current?.focus();
    ref.current?.select();
  }, []);

  const submit = () => {
    const v = ref.current?.value?.trim() || "";
    if (!v) return;
    onConfirm(v);
  };

  return (
    <ModalShell title={title} onClose={onCancel}>
      <label className="block text-xs font-medium text-slate-500">{label}</label>
      <input
        ref={ref}
        className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-sky-500"
        defaultValue={defaultValue}
        placeholder={placeholder}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
        }}
      />
      <div className="mt-5 flex justify-end gap-2">
        <button
          type="button"
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
          onClick={onCancel}
        >
          取消
        </button>
        <button
          type="button"
          className="rounded-lg bg-slate-900 px-3 py-2 text-sm text-white"
          onClick={submit}
        >
          {confirmText}
        </button>
      </div>
    </ModalShell>
  );
}

export function ConfirmModal({
  title,
  message,
  confirmText = "确定",
  danger,
  onCancel,
  onConfirm,
}: {
  title: string;
  message: string;
  confirmText?: string;
  danger?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <ModalShell title={title} onClose={onCancel}>
      <p className="text-sm text-slate-600">{message}</p>
      <div className="mt-5 flex justify-end gap-2">
        <button
          type="button"
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
          onClick={onCancel}
        >
          取消
        </button>
        <button
          type="button"
          className={`rounded-lg px-3 py-2 text-sm text-white ${
            danger ? "bg-rose-600 hover:bg-rose-500" : "bg-slate-900"
          }`}
          onClick={onConfirm}
        >
          {confirmText}
        </button>
      </div>
    </ModalShell>
  );
}
