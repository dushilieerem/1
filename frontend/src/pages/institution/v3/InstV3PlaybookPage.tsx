import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BookOpen } from "lucide-react";
import { dedupeBy } from "@/lib/instDedupe";
import { fetchV3Playbook, type V3Playbook } from "@/lib/instV3Api";

export function InstV3PlaybookPage() {
  const [data, setData] = useState<V3Playbook | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    fetchV3Playbook()
      .then((d) => { if (alive) setData(d); })
      .catch((e: Error) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  if (loading) return <div className="v3-loading">正在加载流程与权限…</div>;
  if (error || !data) return <div className="v3-card">加载失败：{error || "数据不可用"}</div>;

  return (
    <>
      <div className="v3-page-head">
        <div>
          <div className="v3-eyebrow">PLAYBOOK / RULES</div>
          <h1>流程与权限</h1>
        </div>
        <Link className="v3-btn ghost" to="/inst/pipeline"><BookOpen className="h-3.5 w-3.5" />返回流水线</Link>
      </div>

      <section className="v3-card">
        <div className="v3-card-head"><div><h2>流程环节</h2><p>从机会发现到投资管理；执行成交是确定性环节，不调用模型。</p></div></div>
        <div className="v3-play-grid">
          {dedupeBy(data.stages, (s) => s.stage_no).map((s) => (
            <div className="v3-play-node" key={s.stage_no}>
              <span className="no">{String(s.stage_no).padStart(2, "0")}</span>
              <b>{s.stage_name}</b>
              <span>{s.gate} · {s.owner}</span>
              {s.steps.length ? <span style={{ marginTop: 4 }}>{s.steps.join(" → ")}</span> : null}
            </div>
          ))}
        </div>
      </section>

      <div className="v3-home-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <section className="v3-card">
          <div className="v3-card-head"><div><h2>审批关卡</h2><p>顺序固定，不可跳级；风控否决终局。</p></div></div>
          {dedupeBy(data.gates, (g) => g.key).map((g, i) => (
            <div className="v3-kv" key={g.key}>
              <dt>{i + 1}. {g.name}</dt>
              <dd>{g.rule}<br /><span className="text-[12px] text-[#6b6370]">{g.actions.join(" / ")}</span></dd>
            </div>
          ))}
        </section>
        <section className="v3-card">
          <div className="v3-card-head"><div><h2>规则</h2><p>版本与证据链的硬约束。</p></div></div>
          <ul className="v3-rule-list">{data.rules.map((r) => <li key={r}>{r}</li>)}</ul>
        </section>
      </div>

      <section className="v3-card">
        <div className="v3-card-head"><div><h2>硬约束</h2><p>任何一项不通过都不能直接放行；要么否决，要么附条件并写清约束。</p></div></div>
        <ul className="v3-rule-list">{data.hard_constraints.map((x) => <li key={x}>{x}</li>)}</ul>
      </section>


      <section className="v3-card">
        <div className="v3-card-head"><div><h2>角色权限矩阵</h2><p>权限由服务端按登录身份执行。</p></div></div>
        <div style={{ overflowX: "auto" }}>
          <table className="v3-table">
            <thead><tr><th>角色</th><th>工作台/流水线</th><th>价值分析</th><th>多空辩论</th><th>投委会审批</th><th>执行成交</th><th>投资管理</th></tr></thead>
            <tbody>
              <tr><td>投资经理</td><td>读写</td><td>写</td><td>写</td><td>只读本人</td><td>执行</td><td>写</td></tr>
              <tr><td>合伙人</td><td>只读</td><td>—</td><td>—</td><td>第一关</td><td>—</td><td>—</td></tr>
              <tr><td>风控</td><td>只读</td><td>—</td><td>—</td><td>第二关</td><td>—</td><td>—</td></tr>
              <tr><td>Chairman</td><td>只读</td><td>—</td><td>—</td><td>第三关</td><td>—</td><td>—</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="v3-card">
        <div className="v3-card-head"><div><h2>退出回路</h2><p>退出和买入一样重；不复用买入授权。</p></div></div>
        <div className="v3-play-grid">
          {["盘中监控", "记录预警", "投委会复核", "退出议案", "重走三关", "新授权执行"].map((x, i) => (
            <div className="v3-play-node" key={x}><b>{x}</b><span>{i < 2 ? "监控 Agent" : "人工 / 审批"}</span></div>
          ))}
        </div>
      </section>
      <section className="v3-card">
        <div className="v3-card-head"><div><h2>证据分级</h2><p>重大结论需 A 级证据，或独立 B 级证据；D 级不得支撑买入。</p></div></div>
        <div className="v3-play-grid">
          {dedupeBy(data.evidence_grades, (e) => e.grade).map((e) => (
            <div className="v3-play-node" key={e.grade}>
              <span className="no">{e.grade} 级</span>
              <b>{e.source}</b>
              <span>{e.rule}</span>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
