import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, Filter } from "lucide-react";
import { dedupeBy } from "@/lib/instDedupe";
import { useInstSession } from "@/components/institution/instSessionContext";
import { deleteV3Case, fetchV3Pipeline, type V3Pipeline, type V3PipelineItem } from "@/lib/instV3Api";

function ProjectCard({
  item,
  deleting,
  canDelete,
  onDelete,
}: {
  item: V3PipelineItem;
  deleting: boolean;
  canDelete: boolean;
  onDelete: (item: V3PipelineItem) => void;
}) {
  const title = item.company_name || item.symbol || "—";
  const opportunity = (item.opportunity || {}) as { source_label?: string };
  const stageLine = item.stage_no === 0
    ? "当前阶段：机会发现 · 待进入价值分析"
    : `当前阶段：${item.stage_name}`;
  const target = item.is_holding && item.symbol
    ? `/inst/manage?key=${encodeURIComponent(`holding:${item.symbol}`)}`
    : `/inst/pipeline/result?key=${encodeURIComponent(item.key)}`;
  return (
    <div className="v3-project">
      <Link className="v3-project-link" to={target}>
        <span className="nm">{title}{item.is_exit ? <span className="v3-chip bad">退出案</span> : null}{item.is_holding ? <span className="v3-chip ok">持仓中</span> : null}<span className="v3-chip gold">{item.stage_name}</span>{item.stage_no > 0 ? <span className="v3-chip">版本 {item.version_no ?? "—"}</span> : null}</span>
        <span className="cd">{item.symbol} {item.industry ? `· ${item.industry}` : ""}</span>
        <span className="ms">{stageLine}</span>
        <span className="ft">
          <span className="v3-chip">{item.stage_no === 0 ? opportunity.source_label || "自选" : item.version_status || item.proposal_status || "—"}</span>
          <ArrowRight className="h-3 w-3 text-[#6b6370]" />
        </span>
      </Link>
      {item.case_id && item.stage_no < 4 && canDelete ? (
        <div className="v3-project-actions">
          <button
            type="button"
            className="v3-project-del"
            disabled={deleting}
            onClick={() => onDelete(item)}
          >
            {deleting ? "删除中…" : item.is_exit ? "取消退出案" : "删除研究案"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function InstV3PipelinePage() {
  const [params] = useSearchParams();
  const session = useInstSession();
  const q = (params.get("q") || "").trim().toLowerCase();
  const [data, setData] = useState<V3Pipeline | null>(null);
  const [stage, setStage] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchV3Pipeline()
      .then((d) => { if (alive) setData(d); })
      .catch((e: Error) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  async function handleDelete(item: V3PipelineItem) {
    if (!item.case_id) return;
    const label = item.company_name || item.symbol || "该研究案";
    const prompt = item.is_exit
      ? `确定取消「${label}」的退出案？退出案与关联议案会关闭，持仓保留，历史审计保留。`
      : `确定删除「${label}」的研究案？删除后从流水线移除，历史审计与版本保留；有持仓、有效授权或在途议案时会被拒绝。`;
    if (!window.confirm(prompt)) return;
    setDeleting(item.case_id);
    setActionError(null);
    try {
      await deleteV3Case(item.case_id);
      setData(await fetchV3Pipeline());
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "删除失败");
    } finally {
      setDeleting(null);
    }
  }

  const stages = useMemo(() => {
    if (!data) return [];
    return data.stages.map((s) => ({
      ...s,
      items: dedupeBy(s.items.filter((x) => {
        if (!q) return true;
        const hay = `${x.company_name || ""} ${x.symbol || ""} ${x.industry || ""}`.toLowerCase();
        return hay.includes(q);
      }), (x) => x.key),
    }));
  }, [data, q]);

  if (loading) return <div className="v3-loading">正在加载项目流水线…</div>;
  if (error || !data) return <div className="v3-card">加载失败：{error || "数据不可用"}</div>;

  const shown = stage == null ? stages : stages.filter((s) => s.stage_no === stage);

  return (
    <>
      <div className="v3-page-head">
        <div>
          <div className="v3-eyebrow">PIPELINE</div>
          <h1>项目流水线</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link className="v3-btn ghost" to="/inst/playbook">流程说明</Link>
        </div>
      </div>

      <div className="v3-rail">
        <button className={`v3-rail-cell${stage === null ? " on" : ""}`} onClick={() => setStage(null)}>
          <span className="no">ALL</span><span className="nm">全流程 · {data.stages.length} 个环节</span><span className="ct">{data.total}<small>个项目</small></span>
        </button>
        {data.stages.map((s) => (
          <button key={s.stage_no} className={`v3-rail-cell${stage === s.stage_no ? " on" : ""}`} onClick={() => setStage(stage === s.stage_no ? null : s.stage_no)}>
            <span className="no">{String(s.stage_no).padStart(2, "0")}</span>
            <span className="nm">{s.stage_name}</span>
            <span className="ct">{s.truncated ? `${s.count} / ${s.total_count ?? s.count}` : s.count}<small>个</small></span>
          </button>
        ))}
      </div>

      <section className="v3-card">
        <div className="v3-card-head">
          <div><h2><Filter className="mr-1 inline h-4 w-4" />项目进展</h2><p>按 {data.stages.length} 个环节展示；点卡片进入只读结果页。</p></div>
          {q ? <span className="v3-chip info">筛选：{q}</span> : null}
        </div>
        {actionError ? <div className="v3-note" style={{ marginBottom: 10 }}>{actionError}</div> : null}
        {shown.length ? (
          <div className={`v3-board${stage !== null ? " single" : ""}`}>
            {shown.map((s) => (
              <div className="v3-col" key={s.stage_no}>
                <div className="v3-col-head"><b>{s.stage_name}</b><span>{s.items.length}</span></div>
                <div className={`v3-col-items${stage !== null ? " horizontal" : ""}`}>
                  {s.items.map((item) => (
                    <ProjectCard
                      key={item.key}
                      item={item}
                      deleting={deleting === item.case_id}
                      canDelete={session.role === "manager"}
                      onDelete={handleDelete}
                    />
                  ))}
                  {!s.items.length ? <div className="v3-empty" style={{ padding: "16px" }}>暂无项目</div> : null}
                </div>
              </div>
            ))}
          </div>
        ) : <div className="v3-empty">没有匹配的项目。</div>}
      </section>
    </>
  );
}
