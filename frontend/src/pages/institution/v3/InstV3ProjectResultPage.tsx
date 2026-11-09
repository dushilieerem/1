import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, Lock, ShieldCheck } from "lucide-react";
import { fetchV3Project, type V3Result } from "@/lib/instV3Api";

const STAGES = [
  { no: 0, name: "机会发现", gate: "立项三问" },
  { no: 1, name: "价值分析", gate: "研究定稿" },
  { no: 2, name: "多空辩论", gate: "议案锁定" },
  { no: 3, name: "投委会审批", gate: "三关审批" },
  { no: 4, name: "执行成交", gate: "授权执行" },
  { no: 5, name: "投资管理", gate: "监控 / 退出" },
];

function text(v: unknown, fallback = "—"): string {
  if (v === null || v === undefined || v === "") return fallback;
  return String(v);
}

function stageLink(key: string, stageNo: number): string {
  if (stageNo === 0) return `/inst/research?key=${encodeURIComponent(key)}`;
  if (stageNo === 1) return `/inst/research?key=${encodeURIComponent(key)}`;
  if (stageNo === 2) return `/inst/debate?key=${encodeURIComponent(key)}`;
  if (stageNo === 3) return `/inst/approvals?key=${encodeURIComponent(key)}`;
  if (stageNo === 4) return `/inst/execute?key=${encodeURIComponent(key)}`;
  return `/inst/manage?key=${encodeURIComponent(key)}`;
}

export function InstV3ProjectResultPage() {
  const [params] = useSearchParams();
  const key = params.get("key") || "";
  const [data, setData] = useState<V3Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    if (!key) { setLoading(false); setError("缺少项目 key"); return () => { alive = false; }; }
    fetchV3Project(key)
      .then((d) => { if (alive) setData(d); })
      .catch((e: Error) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [key]);

  const company = useMemo(() => {
    if (!data) return {} as Record<string, unknown>;
    return (data.company || (data.case as Record<string, unknown>) || {}) as Record<string, unknown>;
  }, [data]);

  if (loading) return <div className="v3-loading">正在加载项目结果…</div>;
  if (error || !data) return <div className="v3-card">加载失败：{error || "项目不存在"}</div>;

  const stageNo = Number(data.stage_no || 0);
  const title = text(company.name || company.company_name, key);
  const symbol = text(company.symbol, "");
  const version = (data.latest_version || {}) as Record<string, unknown>;
  const proposal = (data.latest_proposal || {}) as Record<string, unknown>;
  const auth = (data.authorization || {}) as Record<string, unknown>;
  const position = (data.position || {}) as Record<string, unknown>;
  const idea = (data.idea || {}) as Record<string, unknown>;
  const locks = (data.locks || {}) as Record<string, unknown>;

  return (
    <>
      <div className="v3-page-head">
        <div>
          <Link className="v3-eyebrow inline-flex items-center gap-1" to="/inst/pipeline"><ArrowLeft className="h-3 w-3" />返回项目流水线</Link>
          <h1>{title} <span className="font-mono text-[12px] font-normal text-[#6b6370]">{symbol}</span></h1>
        </div>
        <Link className="v3-btn primary" to={stageLink(key, stageNo)}>
          进入{stageNo === 0 ? "价值分析" : STAGES[Math.min(5, Math.max(0, stageNo))].name}工作台 <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>

      <div className="v3-stepper">
        {STAGES.map((s) => (
          <div key={s.no} className={`v3-step${s.no < stageNo ? " done" : s.no === stageNo ? " now" : ""}`}>
            <span className="dot">{s.no < stageNo ? "✓" : s.no}</span>
            <div><span className="lb">{s.name}</span><span className="sb">{s.gate}</span></div>
          </div>
        ))}
      </div>

      <div className="v3-result-grid">
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <section className="v3-card">
            <div className="v3-card-head">
              <div><h2>当前阶段结论</h2><p>{data.stage_name} · {data.stage_state === "returned" ? "已退回" : "进行中"}</p></div>
              <span className={`v3-chip ${data.stage_state === "returned" ? "warn" : "info"}`}>{data.stage_name}</span>
            </div>
            {stageNo === 0 ? (
              <div>
                <dl>
                  <div className="v3-kv"><dt>为什么是现在</dt><dd>{text(idea.why_now)}</dd></div>
                  <div className="v3-kv"><dt>能力圈</dt><dd>{text(idea.circle_of_competence)}</dd></div>
                  <div className="v3-kv"><dt>资料齐备度</dt><dd>{text(idea.data_sufficiency)}</dd></div>
                  <div className="v3-kv"><dt>AI 建议</dt><dd>{text(idea.suggestion)}</dd></div>
                </dl>
                {Array.isArray(idea.data_gaps) && idea.data_gaps.length ? <div className="v3-note" style={{ marginTop: 8 }}>数据缺口：{(idea.data_gaps as unknown[]).map(String).join("；")}</div> : null}
              </div>
            ) : (
              <div>
                <dl>
                  <div className="v3-kv"><dt>研究版本</dt><dd>{version.version_no ? `R${version.version_no} · ${text(version.status)}` : "—"}</dd></div>
                  <div className="v3-kv"><dt>研究结论</dt><dd>{text(version.conclusion || data.case && (data.case as Record<string, unknown>).conclusion)}</dd></div>
                  <div className="v3-kv"><dt>议案</dt><dd>{proposal.status ? `${text(proposal.status)} · ${text(proposal.direction)} ${proposal.target_weight ? `${(Number(proposal.target_weight) * 100).toFixed(1)}%` : ""}` : "—"}</dd></div>
                  <div className="v3-kv"><dt>授权</dt><dd>{auth.id ? `${text(auth.status)} · ${text(auth.issued_at)}` : "—"}</dd></div>
                  <div className="v3-kv"><dt>持仓</dt><dd>{position.symbol ? `${text(position.qty)} 股 · 权重 ${(Number(position.weight || 0) * 100).toFixed(1)}%` : "尚未成交"}</dd></div>
                </dl>
                {data.stage_state === "returned" ? <div className="v3-note" style={{ marginTop: 8 }}>该阶段被退回：请回到对应工作台补材料后重新提交，旧锁定版本不再作为下游依据。</div> : null}
              </div>
            )}
          </section>

          <section className="v3-card">
            <div className="v3-card-head"><div><h2>版本与锁定</h2><p>下游只读引用，不复制、不改写；上游变更触发下游作废重跑。</p></div></div>
            <dl>
              <div className="v3-kv"><dt>研究锁定</dt><dd>{locks.research ? `已锁定 · ${text((locks.research as Record<string, unknown>).locked_at)}` : "未锁定"}</dd></div>
              <div className="v3-kv"><dt>议案锁定</dt><dd>{locks.proposal ? `已锁定 · ${text((locks.proposal as Record<string, unknown>).locked_at)}` : "未锁定"}</dd></div>
              <div className="v3-kv"><dt>授权 AUTH</dt><dd>{auth.snapshot ? "不可修改快照已生成" : "未生成"}</dd></div>
            </dl>
            <div className="v3-note" style={{ marginTop: 8 }}><Lock className="mr-1 inline h-3 w-3" />研究定稿、议案、授权逐级锁定；要改上游必须回工作台重跑，下游版本自动作废。</div>
          </section>
        </div>

        <aside style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <section className="v3-card">
            <div className="v3-card-head"><div><h2><ShieldCheck className="mr-1 inline h-4 w-4" />下一关</h2><p>{STAGES[Math.min(5, Math.max(0, stageNo))].gate}</p></div></div>
            <p style={{ fontSize: 12, lineHeight: 1.7, color: "#5f5766" }}>
              {stageNo >= 5 ? "进入投资管理：监控 Agent 持续跟踪，异常或风控预警时通知负责人决定是否卖出。" : `进入${STAGES[Math.min(5, Math.max(0, stageNo))].name}工作台，按步骤完成本环节；结果页只读。`}
            </p>
            <Link className="v3-btn primary" style={{ marginTop: 8, width: "100%" }} to={stageLink(key, stageNo)}>进入工作台</Link>
          </section>
          <section className="v3-card">
            <div className="v3-card-head"><div><h2>项目信息</h2></div></div>
            <dl>
              <div className="v3-kv"><dt>项目</dt><dd>{key}</dd></div>
              <div className="v3-kv"><dt>阶段</dt><dd>{data.stage_no}</dd></div>
              <div className="v3-kv"><dt>行业</dt><dd>{text(company.industry)}</dd></div>
              <div className="v3-kv"><dt>数据状态</dt><dd>{text(company.data_status)}</dd></div>
            </dl>
          </section>
        </aside>
      </div>
    </>
  );
}
