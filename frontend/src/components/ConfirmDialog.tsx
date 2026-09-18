import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ConfirmOptions = {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** 确认按钮用危险色（删除等） */
  danger?: boolean;
  /** 仅「确定」按钮（成功提示等） */
  alert?: boolean;
};

type AskConfirm = (opts: ConfirmOptions | string) => Promise<boolean>;

const ConfirmContext = createContext<AskConfirm | null>(null);

type Pending = ConfirmOptions & { resolve: (ok: boolean) => void };

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);

  const ask = useCallback<AskConfirm>((opts) => {
    const normalized: ConfirmOptions =
      typeof opts === "string" ? { message: opts } : opts;
    return new Promise<boolean>((resolve) => {
      setPending({
        title: normalized.title,
        message: normalized.message,
        confirmLabel: normalized.confirmLabel || "确定",
        cancelLabel: normalized.cancelLabel || "取消",
        danger: !!normalized.danger,
        alert: !!normalized.alert,
        resolve,
      });
    });
  }, []);

  const finish = useCallback((ok: boolean) => {
    setPending((cur) => {
      cur?.resolve(ok);
      return null;
    });
  }, []);

  const value = useMemo(() => ask, [ask]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      {pending ? (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center bg-slate-900/40 px-4"
          role="presentation"
          onClick={() => finish(!!pending.alert)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={pending.title ? "app-confirm-title" : undefined}
            aria-describedby="app-confirm-msg"
            className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-xl shadow-slate-900/10 animate-fade-up"
            onClick={(e) => e.stopPropagation()}
          >
            {pending.title ? (
              <h2
                id="app-confirm-title"
                className="text-base font-semibold text-slate-900"
              >
                {pending.title}
              </h2>
            ) : null}
            <p
              id="app-confirm-msg"
              className={`text-sm leading-relaxed text-slate-600 ${
                pending.title ? "mt-2" : ""
              }`}
            >
              {pending.message}
            </p>
            <div className="mt-5 flex justify-end gap-2">
              {!pending.alert ? (
                <button
                  type="button"
                  autoFocus
                  onClick={() => finish(false)}
                  className="rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                >
                  {pending.cancelLabel}
                </button>
              ) : null}
              <button
                type="button"
                autoFocus={!!pending.alert}
                onClick={() => finish(true)}
                className={`rounded-lg px-3.5 py-2 text-sm font-semibold text-white transition ${
                  pending.danger
                    ? "bg-red-500 hover:bg-red-400"
                    : "bg-slate-900 hover:bg-slate-800"
                }`}
              >
                {pending.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): AskConfirm {
  const ask = useContext(ConfirmContext);
  if (!ask) {
    throw new Error("useConfirm 需在 ConfirmProvider 内使用");
  }
  return ask;
}
