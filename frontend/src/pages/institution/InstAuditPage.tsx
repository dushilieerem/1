import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ScrollText } from "lucide-react";
import { instApi, fmtDateTime } from "@/lib/instApi";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, Empty, ErrorBox, Loading, PageHeader } from "./instUi";

type AuditRow = {
  id: number;
  action: string;
  object_type?: string;
  object_id?: number;
  actor_member_id?: number;
  actor_name?: string;
  actor_role?: string;
  policy_version?: string;
  ip?: string;
  created_at?: string;
  after?: Record<string, unknown> | null;
};

const ACTION_LABEL: Record<string, [string, string]> = {
  "research.case.create": ["创建研究案", "Research case created"],
  "research.generate": ["生成研究", "Research generated"],
  "research.review.approve": ["研究审核通过", "Research approved"],
  "research.review.return": ["研究退回", "Research returned"],
  "research.review.dimension.approve": ["单维审核通过", "Dimension approved"],
  "research.review.dimension.reject": ["单维审核不通过", "Dimension rejected"],
  "research.dimension.chat": ["单维追问", "Dimension question"],
  "debate.complete": ["辩论完成", "Debate completed"],
  "proposal.create": ["创建议案", "Proposal created"],
  "proposal.partner.approve": ["合伙人复核通过", "Partner approved"],
  "proposal.partner.return": ["合伙人退回", "Partner returned"],
  "proposal.chairman.approve": ["Chairman 通过", "Chairman approved"],
  "proposal.chairman.conditional": ["Chairman 附条件通过", "Chairman conditionally approved"],
  "proposal.chairman.reject": ["Chairman 拒绝", "Chairman rejected"],
  "proposal.chairman.return": ["Chairman 退回", "Chairman returned"],
  "proposal.risk.pass": ["风控通过", "Risk passed"],
  "proposal.risk.block": ["风控阻断", "Risk blocked"],
  "proposal.authorize": ["生成授权", "Authorization created"],
  "authorization.execute": ["模拟成交", "Simulated fill"],
  "authorization.execute.blocked": ["成交阻断", "Fill blocked"],
  "monitor.exit.create": ["发起退出研究", "Exit research started"],
  "monitor.exit.submit": ["退出案提交", "Exit case submitted"],
  "monitor.exit.approve": ["退出案通过", "Exit case approved"],
  "monitor.exit.reject": ["退出案拒绝", "Exit case rejected"],
  "monitor.exit.risk_block": ["退出案风控阻断", "Exit case risk-blocked"],
  "monitor.exit.authorize": ["退出案授权", "Exit case authorized"],
  "monitor.exit.close": ["退出案关闭", "Exit case closed"],
  "monitor.exit.review": ["退出复盘", "Exit post-mortem"],
  "monitor.event.create": ["记录监控预警", "Monitor alert logged"],
  "company.pool_status": ["更新公司池状态", "Pool status updated"],
};

const OBJECT_LABEL: Record<string, [string, string]> = {
  inst_research_case: ["研究案", "Research case"],
  inst_research_version: ["研究版本", "Research version"],
  inst_research_task: ["研究任务", "Research task"],
  inst_proposal: ["议案", "Proposal"],
  inst_authorization: ["授权", "Authorization"],
  inst_order: ["订单", "Order"],
  inst_exit_case: ["退出案", "Exit case"],
  inst_company: ["公司", "Company"],
  inst_monitor_event: ["监控事件", "Monitor event"],
  inst_thesis_ledger: ["论点台账", "Thesis ledger"],
};

const ROLE_LABEL: Record<string, [string, string]> = {
  manager: ["投资经理", "Manager"],
  partner: ["合伙人", "Partner"],
  chairman: ["Chairman", "Chairman"],
  risk: ["独立风控", "Risk"],
  execution: ["交易执行", "Execution"],
  monitoring: ["组合监控", "Monitoring"],
};

const FIELD_LABEL: Record<string, string> = {
  status: "状态",
  version_no: "版本",
  case_id: "研究案",
  proposal_id: "议案",
  direction: "方向",
  target_weight: "目标仓位",
  mode: "模式",
  key: "维度",
  decision: "决定",
  comment: "意见",
  order_id: "订单",
  authorization_id: "授权",
  merged_from_version_no: "合并自版本",
  agents: "Agent 状态",
  thesis_verdict: "论点结论",
  realized_return: "已实现收益",
  pool_status: "公司池状态",
  reason_type: "退出原因",
};

const VALUE_LABEL: Record<string, string> = {
  draft: "草稿",
  pending_review: "待审核",
  approved: "已通过",
  changed: "已退回",
  researching: "研究中",
  proposal: "已进入议案",
  submitted: "已提交",
  closed: "已关闭",
  partner_review: "待合伙人复核",
  chairman_review: "待 Chairman 审批",
  risk_precheck: "待执行前风控",
  authorized: "已授权",
  executed: "已执行",
  rejected: "已拒绝",
  frozen: "风控冻结",
  buy: "买入",
  sell: "卖出",
  exit: "退出",
  approve: "通过",
  conditional: "附条件通过",
  pass: "通过",
  block: "阻断",
  veto: "否决",
  return: "退回",
  watch: "观察中",
  research: "研究中",
  dropped: "已放弃",
  thesis_invalid: "论点失效",
  valuation: "估值透支",
  better_allocation: "更优资本配置",
  portfolio_constraint: "组合/资金约束",
  other: "其他",
};

function label(map: Record<string, [string, string]>, key: string, locale: string): string {
  const item = map[key];
  if (item) return locale === "en" ? item[1] : item[0];
  return key;
}

function valueLabel(key: string, value: unknown, locale: string): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? (locale === "en" ? "yes" : "是") : locale === "en" ? "no" : "否";
  if (typeof value === "object") return JSON.stringify(value);
  const text = String(value);
  if (key === "target_weight") {
    const n = Number(text);
    return Number.isFinite(n) ? `${(n * 100).toFixed(2)}%` : text;
  }
  const mapped = VALUE_LABEL[text];
  if (mapped) return locale === "en" ? text : mapped;
  return text;
}

function summarise(
  after: Record<string, unknown> | null | undefined,
  locale: string,
): string {
  if (!after) return "—";
  const parts = Object.entries(after)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .slice(0, 4)
    .map(([k, v]) => `${locale === "en" ? k : FIELD_LABEL[k] || k}：${valueLabel(k, v, locale)}`);
  return parts.length ? parts.join(" · ") : "—";
}

export function InstAuditPage() {
  const { locale, t } = useInstLocale();
  const [items, setItems] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    instApi<{ items: AuditRow[] }>("/audit?limit=200")
      .then((d) => setItems(d.items || []))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="AUDIT"
        title={t("审计日志", "Audit log")}
        desc={t(
          "只增不改的机构端操作记录：时间、角色、动作、对象与结果。",
          "Append-only institutional audit trail: time, actor, action, object and result.",
        )}
        actions={
          <Link to="/inst/overview">
            <Button variant="ghost">
              <ArrowLeft className="mr-1 h-4 w-4" /> {t("返回驾驶舱", "Back to cockpit")}
            </Button>
          </Link>
        }
      />
      {error ? <ErrorBox message={error} onRetry={load} /> : null}
      {loading ? (
        <Loading label={t("正在加载审计日志…", "Loading audit log…")} />
      ) : items.length ? (
        <Card
          title={t("最近 200 条", "Latest 200")}
          desc={t("按时间倒序；动作、对象和字段已转成中文。", "Newest first; actions, objects and fields are human-readable.")}
          actions={<Badge tone="gold">{items.length} {t("条", "items")}</Badge>}
        >
          <ul className="divide-y divide-[#e3eaf8]">
            {items.map((row) => (
              <li key={row.id} className="py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium text-[#252533]" title={row.action}>
                    {label(ACTION_LABEL, row.action, locale)}
                  </span>
                  <span className="text-[10px] text-[#77718c]">{fmtDateTime(row.created_at)}</span>
                </div>
                <p className="mt-1 text-[11px] text-[#68738b]">
                  {row.object_type ? label(OBJECT_LABEL, row.object_type, locale) : t("对象", "Object")}
                  {row.object_id != null ? ` #${row.object_id}` : ""} · {t("操作人", "Actor")}{" "}
                  {row.actor_name || (row.actor_member_id != null ? `#${row.actor_member_id}` : t("系统", "System"))}
                  {row.actor_role ? `（${label(ROLE_LABEL, row.actor_role, locale)}）` : ""} ·{" "}
                  {row.policy_version === "demo-v1" ? t("演示政策 v1", "Demo policy v1") : row.policy_version || "—"}
                  {row.ip ? ` · ${row.ip}` : ""}
                </p>
                <p className="mt-1 break-all text-[10px] leading-relaxed text-[#77718c]">
                  {summarise(row.after, locale)}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      ) : (
        <Empty>
          <ScrollText className="mx-auto mb-2 h-6 w-6 text-[#a9a4bd]" />
          {t("还没有审计记录。", "No audit records yet.")}
        </Empty>
      )}
    </div>
  );
}
