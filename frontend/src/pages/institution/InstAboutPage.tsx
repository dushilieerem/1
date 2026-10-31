import { BadgeCheck, ShieldCheck, Users } from "lucide-react";
import { useInstSession } from "@/components/institution/instSessionContext";
import { Badge, Card, PageHeader } from "./instUi";

const ROLES = [
  ["投资经理", "发现机会、组织研究、提交建议、投后跟踪、发起退出", "可提案；不得批准自己的议案、不得下单"],
  ["合伙人", "复核研究、设计组合与仓位、上报审批", "可配置与上报；不得自批、自执行"],
  ["Chairman", "最终资本配置与重大退出审议", "可批准、附条件批准、退回、拒绝；不得改仓位、不得绕开风控、不得下单"],
  ["独立风控", "风险检查、整改、冻结、执行前复核", "可否决与冻结；不得制定仓位、不得代替 Chairman 批准"],
  ["交易执行", "校验授权、纸面或券商执行、成交与对账", "只执行有效授权；不得修改标的、方向、仓位"],
  ["组合监控", "持仓、敞口、收益、异常监控", "可报告与提交复核；不得审批、不得交易"],
];

const AI_ROLES = [
  ["研究统筹 / 机会发现", "拆解研究任务、汇总证据与未知事项、提出立项/观察/放弃建议"],
  ["产业 / 商业模式 / 护城河", "行业结构、单位经济性、竞争优势与侵蚀路径"],
  ["财务与取证", "三表勾稽、ROIC/FCF、应收存货与会计风险"],
  ["治理 / 估值 / 反证", "资本配置、DCF 与敏感性、可检验的反证条件"],
  ["看多 / 看空 / 主持", "基于同一 FactPack 独立立论、交叉质询、保留异议"],
  ["风控 / 合规 / 交易", "阈值检查、版本一致性、授权校验与对账"],
  ["投后 / 退出 / 复盘", "论点台账、经营预警、退出备忘录与归因"],
];

export function InstAboutPage() {
  const session = useInstSession();
  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="ABOUT / 09"
        title="关于我们"
        desc={`${session.org.name_cn} · SVQuant 机构端 · 主观价值投资。本期为演示环境，无真实资金交易。`}
        actions={<Badge tone="gold">{session.role_label_cn}</Badge>}
      />

      <Card
        title="角色与职责边界"
        desc="权限以服务端为准；前端隐藏菜单不是安全边界。提案人与批准人、研究与风控、审批与执行必须分离。"
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-[#f0ece2] text-[11px] text-slate-400">
                <th className="py-2">角色</th>
                <th className="py-2">核心职责</th>
                <th className="py-2">权限边界</th>
              </tr>
            </thead>
            <tbody>
              {ROLES.map(([role, duty, boundary]) => (
                <tr key={role} className="border-b border-[#f7f4ec] last:border-0">
                  <td className="whitespace-nowrap py-3 font-medium text-slate-800">{role}</td>
                  <td className="py-3 text-xs leading-relaxed text-slate-600">{duty}</td>
                  <td className="py-3 text-xs leading-relaxed text-slate-500">{boundary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="AI 角色与能力" desc="25 个岗位按七阶段组织；AI 只给建议，不改变业务状态。">
          <ul className="space-y-3">
            {AI_ROLES.map(([name, desc]) => (
              <li key={name} className="rounded-xl border border-[#f0ece2] bg-[#faf9f5] p-3">
                <p className="text-sm font-medium text-slate-800">{name}</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-500">{desc}</p>
              </li>
            ))}
          </ul>
        </Card>

        <div className="space-y-4">
          <Card title="硬约束" desc="这些规则在服务端执行，任何角色与 AI 都不能绕过。">
            <ul className="space-y-2 text-xs leading-relaxed text-slate-600">
              <li className="flex gap-2"><ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#8a6a2f]" />单股目标仓位 ≤ 15%，交易后现金 ≥ 10%（内部演示政策，不是监管限额）。</li>
              <li className="flex gap-2"><BadgeCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#8a6a2f]" />提案人不得审批自己的议案；合伙人不得批准自己提交的最终配置。</li>
              <li className="flex gap-2"><Users className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#8a6a2f]" />授权是不可变快照；研究、仓位、价格、账户、汇率、有效期发生实质变更，旧批准与授权自动失效。</li>
              <li className="flex gap-2"><ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#8a6a2f]" />风控否决终局；冻结期间 Chairman 不能批准，解除须独立风控重新核验。</li>
            </ul>
          </Card>

          <Card title="免责声明">
            <p className="text-xs leading-relaxed text-slate-500">
              本平台为研究与流程演示，不构成投资建议、不承诺收益、不代客理财、不接真实资金交易。
              原型与研究数据中的公司、价格、财务、证据与仓位仅用于验证流程；演示数据不得进入真实审批。
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
