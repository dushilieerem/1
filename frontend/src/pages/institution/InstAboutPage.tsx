import { BadgeCheck, ChevronDown, ShieldCheck, Users } from "lucide-react";
import { useInstSession } from "@/components/institution/instSessionContext";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Card, PageHeader } from "./instUi";
import { InstAgentsPanel } from "./InstAgentsPanel";

const ROLES: Array<[string, string, string, string, string, string]> = [
  ["投资经理", "Portfolio manager", "发现机会、组织研究、提交建议、投后跟踪、发起退出", "Originate, organize research, propose, monitor and initiate exits", "可提案；不得批准自己的议案、不得下单", "Can propose; cannot approve own proposals or place orders"],
  ["合伙人", "Partner", "复核研究、设计组合与仓位、上报审批", "Review research, design portfolio and sizing, escalate for approval", "可配置与上报；不得自批、自执行", "Can size and escalate; cannot self-approve or self-execute"],
  ["Chairman", "Chairman", "最终资本配置与重大退出审议", "Final capital allocation and major exit decisions", "可批准、附条件批准、退回、拒绝；不得改仓位、不得绕开风控、不得下单", "Can approve, condition, return or reject; cannot resize, bypass risk or trade"],
  ["独立风控", "Independent risk", "风险检查、整改、冻结、执行前复核", "Risk checks, remediation, freeze, pre-execution review", "可否决与冻结；不得制定仓位、不得代替 Chairman 批准", "Can veto and freeze; cannot size or approve for Chairman"],
  ["交易执行", "Execution", "校验授权、纸面或券商执行、成交与对账", "Validate authorization, paper/broker execution, fills and reconciliation", "只执行有效授权；不得修改标的、方向、仓位", "Executes qualified authorizations only; cannot change symbol, direction or size"],
  ["组合监控", "Monitoring", "持仓、敞口、收益、异常监控", "Monitor holdings, exposure, returns and anomalies", "可报告与提交复核；不得审批、不得交易", "Can report and request review; cannot approve or trade"],
];

/** 机构端 Agent 管理（替代原 Agent 能力页）。 */
export function InstAboutPage() {
  const session = useInstSession();
  const { locale, t } = useInstLocale();
  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="AGENTS / 09"
        title={t("Agent 管理", "Agent management")}
        desc={`${locale === "en" ? session.org.name_en || session.org.name_cn : session.org.name_cn} · ${t("查看系统内全部 Agent，维护机构/平台提示词；AI 只给建议，不改业务状态。", "View all agents and maintain institution/platform prompts; AI advises and never changes business state.")}`}
        actions={<Badge tone="gold">{locale === "en" ? session.role_label_en : session.role_label_cn}</Badge>}
      />

      <InstAgentsPanel />

      <details className="group rounded-xl border border-[#dde5f2] bg-white p-4">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-sm font-medium text-[#252533]">
          <span>{t("角色与职责边界", "Roles & boundaries")}</span>
          <ChevronDown className="h-4 w-4 text-[#77718c] transition group-open:rotate-180" />
        </summary>
        <p className="mt-2 text-xs leading-relaxed text-[#68738b]">
          {t(
            "权限以服务端为准；前端隐藏菜单不是安全边界。提案人与批准人、研究与风控、审批与执行必须分离。",
            "Permissions are enforced server-side; hidden menus are not a boundary. Proposer/approver, research/risk and approval/execution stay separate.",
          )}
        </p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-[#e3eaf8] text-[11px] text-[#77718c]">
                <th className="py-2">{t("角色", "Role")}</th>
                <th className="py-2">{t("核心职责", "Responsibilities")}</th>
                <th className="py-2">{t("权限边界", "Boundaries")}</th>
              </tr>
            </thead>
            <tbody>
              {ROLES.map(([roleZh, roleEn, dutyZh, dutyEn, boundZh, boundEn]) => (
                <tr key={roleZh} className="border-b border-[#eef1f8] last:border-0">
                  <td className="whitespace-nowrap py-3 font-medium text-[#252533]">{locale === "en" ? roleEn : roleZh}</td>
                  <td className="py-3 text-xs leading-relaxed text-[#68738b]">{locale === "en" ? dutyEn : dutyZh}</td>
                  <td className="py-3 text-xs leading-relaxed text-[#68738b]">{locale === "en" ? boundEn : boundZh}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={t("硬约束", "Hard rules")} desc={t("这些规则在服务端执行，任何角色与 AI 都不能绕过。", "Enforced server-side; no role or AI can bypass them.")}>
          <ul className="space-y-2 text-xs leading-relaxed text-[#68738b]">
            <li className="flex gap-2"><ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#b42345]" />{t("单股目标仓位 ≤ 15%，交易后现金 ≥ 10%（内部演示政策，不是监管限额）。", "Single-name target ≤ 15%, post-trade cash ≥ 10% (internal demo policy, not a regulatory limit).")}</li>
            <li className="flex gap-2"><BadgeCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#b42345]" />{t("提案人不得审批自己的议案；合伙人不得批准自己提交的最终配置。", "Proposers cannot approve their own proposals; partners cannot approve their own final sizing.")}</li>
            <li className="flex gap-2"><Users className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#b42345]" />{t("授权是不可变快照；研究、仓位、价格、账户、汇率、有效期发生实质变更，旧批准与授权自动失效。", "Authorizations are immutable snapshots; material changes to research, size, price, account, FX or validity void prior approvals and authorizations.")}</li>
            <li className="flex gap-2"><ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#b42345]" />{t("风控否决终局；冻结期间 Chairman 不能批准，解除须独立风控重新核验。", "Risk veto is final; Chairman cannot approve while frozen, and unfreezing requires a fresh independent risk review.")}</li>
          </ul>
        </Card>

        <Card title={t("免责声明", "Disclaimer")}>
          <p className="text-xs leading-relaxed text-[#68738b]">
            {t("本平台为研究与流程演示，不构成投资建议、不承诺收益、不代客理财、不接真实资金交易。原型与研究数据中的公司、价格、财务、证据与仓位仅用于验证流程；演示数据不得进入真实审批。", "This platform demonstrates research and workflow only; it is not investment advice, promises no returns, manages no assets and connects to no real trading. Companies, prices, financials, evidence and positions are for process validation; demo data must not enter real approvals.")}
          </p>
        </Card>
      </div>
    </div>
  );
}
