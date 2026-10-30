import { Link } from "react-router-dom";
import { ArrowLeft, Hammer } from "lucide-react";
import { useInstSession } from "@/components/institution/instSessionContext";
import { accessBadge, INST_PLACEHOLDERS } from "@/data/instNav";

export function InstPlaceholderPage({ workspaceKey }: { workspaceKey: string }) {
  const session = useInstSession();
  const workspace = session.workspaces.find((item) => item.key === workspaceKey);
  const meta = INST_PLACEHOLDERS[workspaceKey];
  const badge = workspace ? accessBadge(workspace.access) : null;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="rounded-2xl border border-[#e7e3d8] bg-white p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[11px] tracking-[0.18em] text-[#8a6a2f]">WORKSPACE / NEXT PHASE</p>
            <h1 className="mt-2 font-display text-2xl font-semibold text-slate-900">
              {workspace?.label_cn || "工作区"}
            </h1>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-2.5 py-1 text-[11px] text-slate-500">
            <Hammer className="h-3.5 w-3.5" aria-hidden />
            下一阶段开放
          </span>
        </div>

        <p className="mt-4 text-sm leading-relaxed text-slate-600">
          {meta?.summary || "该工作区尚未开放。"}
        </p>

        {meta?.points?.length ? (
          <ul className="mt-5 space-y-2">
            {meta.points.map((point) => (
              <li key={point} className="flex items-start gap-2 text-sm text-slate-700">
                <span className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[#c9a15e]" />
                {point}
              </li>
            ))}
          </ul>
        ) : null}

        <div className="mt-6 rounded-xl border border-[#f0ece2] bg-[#faf9f5] px-4 py-3 text-[12px] leading-relaxed text-slate-500">
          当前角色「{session.role_label_cn}」的访问级别：
          <span className="mx-1 font-medium text-slate-700">
            {workspace?.access === "write"
              ? "可写与操作"
              : badge
                ? badge === "只读"
                  ? "只读"
                  : "仅关联摘要"
                : "无权限"}
          </span>
          。服务端已按权限矩阵校验；本页仅为占位说明，不代表功能已完成。
        </div>

        <Link
          to="/inst/overview"
          className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-[#8a6a2f] transition-colors hover:text-[#6d5324]"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          返回投资驾驶舱
        </Link>
      </div>
    </div>
  );
}
