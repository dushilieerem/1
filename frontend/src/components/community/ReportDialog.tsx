import { useEffect, useState } from "react";
import {
  REPORT_REASON_OPTIONS,
  type ReportReason,
  type ReportTargetType,
} from "@/lib/communityApi";
import { fieldClassName } from "@/components/community/communityUi";
import { ContentLengthHint } from "./ContentLengthHint";
import { REPORT_DETAIL_LIMIT, lengthError } from "@/lib/communityLimits";

type Phase = "form" | "confirm" | "success";

export function ReportDialog({
  open,
  targetType,
  onClose,
  onSubmit,
}: {
  open: boolean;
  targetType: ReportTargetType;
  onClose: () => void;
  onSubmit: (payload: {
    reason: ReportReason;
    detail: string;
  }) => Promise<void>;
}) {
  const [phase, setPhase] = useState<Phase>("form");
  const [reason, setReason] = useState<ReportReason>("spam");
  const [detail, setDetail] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setPhase("form");
      setReason("spam");
      setDetail("");
      setBusy(false);
      setErr(null);
    }
  }, [open]);

  if (!open) return null;

  const title =
    targetType === "comment" ? "举报评论" : "举报帖子";
  const reasonLabel =
    REPORT_REASON_OPTIONS.find((o) => o.id === reason)?.label || reason;

  const doSubmit = async () => {
    const detailError = lengthError(detail, REPORT_DETAIL_LIMIT, "举报说明");
    if (detailError) {
      setErr(detailError);
      setPhase("form");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await onSubmit({ reason, detail: detail.trim() });
      setPhase("success");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
      setPhase("form");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[200] flex items-start justify-center bg-slate-900/40 px-4 pt-[14vh]"
      role="presentation"
      onClick={() => {
        if (phase === "success") onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="report-dialog-title"
        className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-xl shadow-slate-900/10 animate-fade-up"
        onClick={(e) => e.stopPropagation()}
      >
        {phase === "success" ? (
          <>
            <h2
              id="report-dialog-title"
              className="text-base font-semibold text-slate-900"
            >
              举报已提交
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              感谢反馈。管理员会在管理仓处理，请勿重复提交。
            </p>
            <div className="mt-5 flex justify-end">
              <button
                type="button"
                autoFocus
                onClick={onClose}
                className="rounded-lg bg-slate-900 px-3.5 py-2 text-sm font-semibold text-white hover:bg-slate-800"
              >
                知道了
              </button>
            </div>
          </>
        ) : phase === "confirm" ? (
          <>
            <h2
              id="report-dialog-title"
              className="text-base font-semibold text-slate-900"
            >
              确认提交举报？
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              类型：{title}
              <br />
              原因：{reasonLabel}
              {detail.trim() ? (
                <>
                  <br />
                  说明：{detail.trim().slice(0, 120)}
                  {detail.trim().length > 120 ? "…" : ""}
                </>
              ) : null}
            </p>
            {err ? <p className="mt-2 text-sm text-red-600">{err}</p> : null}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  setErr(null);
                  setPhase("form");
                }}
                className="rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              >
                返回修改
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void doSubmit()}
                className="rounded-lg bg-slate-900 px-3.5 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
              >
                {busy ? "提交中…" : "确认提交"}
              </button>
            </div>
          </>
        ) : (
          <>
            <h2
              id="report-dialog-title"
              className="text-base font-semibold text-slate-900"
            >
              {title}
            </h2>
            <p className="mt-1.5 text-xs text-slate-500">
              选择原因后提交，管理员会在管理仓处理。
            </p>

            <div className="mt-4 space-y-2">
              {REPORT_REASON_OPTIONS.map((opt) => {
                const active = reason === opt.id;
                return (
                  <label
                    key={opt.id}
                    className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
                      active
                        ? "border-red-200 bg-red-50 text-red-700"
                        : "border-slate-200 text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    <input
                      type="radio"
                      name="report-reason"
                      className="accent-red-600"
                      checked={active}
                      onChange={() => setReason(opt.id)}
                    />
                    {opt.label}
                  </label>
                );
              })}
            </div>

            <textarea
              className={fieldClassName("mt-3 min-h-[72px] resize-y")}
              placeholder="补充说明（可选）"
              aria-describedby="report-detail-length"
              aria-invalid={!!lengthError(detail, REPORT_DETAIL_LIMIT, "举报说明")}
              value={detail}
              onChange={(e) => setDetail(e.target.value)}
            />
            <ContentLengthHint id="report-detail-length" value={detail} limit={REPORT_DETAIL_LIMIT} label="举报说明" />

            {err ? (
              <p className="mt-2 text-sm text-red-600">{err}</p>
            ) : null}

            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => {
                  setErr(null);
                  setPhase("confirm");
                }}
                disabled={!!lengthError(detail, REPORT_DETAIL_LIMIT, "举报说明")}
                className="rounded-lg bg-slate-900 px-3.5 py-2 text-sm font-semibold text-white hover:bg-slate-800"
              >
                下一步
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
