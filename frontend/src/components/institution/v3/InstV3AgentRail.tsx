export type AgentPanelDef = {
  id: string;
  name: string;
  code: string;
  model?: string;
  tools?: string;
  output?: string;
  role?: string;
  engine?: boolean;
};

type ContextRow = { label: string; value: string };

export function InstV3AgentRail({
  agents,
  activeId,
  onSelect,
  contextRows = [],
}: {
  agents: AgentPanelDef[];
  activeId: string;
  onSelect: (id: string) => void;
  contextRows?: ContextRow[];
}) {
  if (!agents.length) return null;
  const active = agents.find((x) => x.id === activeId) || agents[0];
  const engine = Boolean(active.engine);
  return (
    <aside className="v3-agent-rail">
      <div className="ar-kicker">{engine ? "本步执行引擎" : "本步 Agent"}</div>
      <div className="ar-head">
        <h3>{engine ? "执行引擎" : "Agent 面板"}</h3>
        <span className="v3-chip">{agents.length > 1 ? `${agents.length} 个角色 · 可切换` : engine ? "确定性服务" : "单角色"}</span>
      </div>
      <div className="v3-agent-picks">
        {agents.map((a) => (
          <button
            key={a.id}
            className={`v3-agent-pick${a.id === active.id ? " on" : ""}`}
            onClick={() => onSelect(a.id)}
            title={a.role}
          >
            <span className="ap-top"><span className="ap-code">{a.code}</span></span>
            <span className="ap-name">{a.name}</span>
            <span className="ap-meta">{a.output || a.role || "—"}</span>
          </button>
        ))}
      </div>
      <div className="v3-agent-detail">
        <div className="ad-head">
          <span className="ad-name">{active.name}</span>
          <span className={`v3-chip ${engine ? "info" : "gold"}`}>{engine ? "非 Agent · 确定性" : "当前 Agent"}</span>
        </div>
        <div className="ad-role">{active.role || "—"}</div>
        <div className="ad-grid">
          <div><div className="ad-k">模型</div><div className="ad-v">{active.model || "—"}</div></div>
          <div><div className="ad-k">状态</div><div className="ad-v" style={{ color: "var(--v3-ok)" }}>已完成</div></div>
          <div><div className="ad-k">工具</div><div className="ad-v">{active.tools || "—"}</div></div>
          <div><div className="ad-k">产出</div><div className="ad-v">{active.output || "—"}</div></div>
        </div>
      </div>
      {contextRows.length ? (
        <div className="v3-agent-context">
          {contextRows.map((r) => (
            <div className="ar-row" key={r.label}><b>{r.label}</b><br />{r.value}</div>
          ))}
        </div>
      ) : null}
    </aside>
  );
}
