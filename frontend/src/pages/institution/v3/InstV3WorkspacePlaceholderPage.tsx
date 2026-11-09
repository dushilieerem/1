import { Link, useLocation, useSearchParams } from "react-router-dom";
import { ArrowLeft, Construction } from "lucide-react";

const TITLES: Record<string, { no: string; name: string; steps: string[]; desc: string }> = {
  research: { no: "02", name: "价值分析", steps: ["行业分析", "六维结论", "一页纸", "研究定稿"], desc: "左侧项目列表 + 中间当前步骤 + 右侧当前 Agent；六维并行、研究定稿 R3。" },
  debate: { no: "03", name: "多空辩论", steps: ["多空立论", "交叉质询", "估值复核", "议案"], desc: "多头/空头/主持/交易员；估值复核为确定性代码，议案 P3 锁定。" },
  approvals: { no: "04", name: "投委会审批", steps: ["议案提交", "合伙人", "风控", "Chairman", "授权"], desc: "按登录角色展示；三关顺序固定，风控否决终局，Chairman 不能越过。" },
  execute: { no: "05", name: "执行成交", steps: ["授权核对", "下单成交", "对账", "持仓更新"], desc: "确定性执行引擎，不调用模型；授权核对、幂等下单、对账、持仓更新。" },
  manage: { no: "06", name: "投资管理", steps: ["组合总览", "单票盘中", "预警与退出"], desc: "组合总览 + 单票盘中；监控 Agent 跟踪事件，退出重走研究/辩论/审批。" },
};

export function InstV3WorkspacePlaceholderPage() {
  const location = useLocation();
  const [params] = useSearchParams();
  const key = params.get("key");
  const path = location.pathname.split("/").filter(Boolean).pop() || "research";
  const meta = TITLES[path] || TITLES.research;

  return (
    <>
      <div className="v3-page-head">
        <div>
          <div className="v3-eyebrow">WORKBENCH / {meta.no}</div>
          <h1>{meta.no} {meta.name}</h1>
          <p>{meta.desc}</p>
        </div>
        <Link className="v3-btn ghost" to="/inst-v3/pipeline"><ArrowLeft className="h-3.5 w-3.5" />返回项目流水线</Link>
      </div>

      <div className="v3-stepper">
        {meta.steps.map((s, i) => (
          <div key={s} className={`v3-step${i === 0 ? " now" : ""}`}>
            <span className="dot">{i + 1}</span>
            <div><span className="lb">{s}</span><span className="sb">待接入</span></div>
          </div>
        ))}
      </div>

      <section className="v3-card">
        <div className="v3-card-head">
          <div><h2><Construction className="mr-1 inline h-4 w-4" />工作台下一批接入</h2><p>v3 外壳、流水线与结果页已就绪；本工作台的步骤、Agent 与操作将在后续 PR 接入现有后端接口。</p></div>
          <span className="v3-chip warn">预览</span>
        </div>
        <p style={{ fontSize: 11, lineHeight: 1.8, color: "#746b7c" }}>
          当前项目：<b>{key || "未指定"}</b>。本页不会修改任何业务状态；需要操作请回到旧版工作台或等待下一批。
        </p>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <Link className="v3-btn primary" to={key ? `/inst-v3/pipeline/result?key=${encodeURIComponent(key)}` : "/inst-v3/pipeline"}>查看结果页</Link>
          <Link className="v3-btn ghost" to="/inst-v3/pipeline">项目流水线</Link>
        </div>
      </section>
    </>
  );
}
