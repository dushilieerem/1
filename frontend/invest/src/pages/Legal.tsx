import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components";
import { useLocale } from "../i18n";

function LegalPage({ title, sub, children }: { title: string; sub: string; children: ReactNode }) {
  const nav = useNavigate();
  const { t } = useLocale();
  return (
    <div className="app">
      <div className="page legal-page">
        <PageHeader title={title} sub={sub} back onBack={() => nav(-1)} />
        <div className="legal">{children}</div>
        <div className="disclaimer">{t("草案 · 公开运行前需法务/合规书面确认", "Draft · written legal/compliance sign-off required before public launch")}</div>
      </div>
    </div>
  );
}

export function Privacy() {
  const { t } = useLocale();
  return (
    <LegalPage title={t("隐私政策", "Privacy Policy")} sub={t("草案 · 2026-10-26", "Draft · 2026-10-26")}>
      <h4>{t("1. 我们收集什么", "1. What we collect")}</h4>
      <p>{t("账号标识、用户名、自选标的、你主动导入的持仓、关注事件、风险测评答案，以及登录/注册/导出/删除等安全审计记录（时间、动作、用户名、IP、摘要）。持仓数据属于敏感信息，仅用于组合体检与风险提示。", "Account identifiers, username, watchlist symbols, holdings you import, watch events, risk assessment answers, and security audit records for login/registration/export/deletion (time, action, username, IP, summary). Holdings are sensitive information and are used only for portfolio checkups and risk warnings.")}</p>
      <h4>{t("2. 我们如何使用", "2. How we use it")}</h4>
      <p>{t("用于提供行情、财务、估值、组合诊断、事件日志、安全审计与产品改进；不用于公共模型训练，不向第三方出售，不用于广告画像。公开版如接入第三方数据/客服/统计分析，会在此列明接收方与目的。", "Used to provide quotes, financials, valuation, portfolio diagnostics, event logs, security audits, and product improvements; not used for public model training, not sold to third parties, and not used for advertising profiles. If the public version integrates third-party data/support/analytics, the recipients and purposes will be listed here.")}</p>
      <h4>{t("3. 保存与删除", "3. Retention and deletion")}</h4>
      <p>{t("你可以在「我的」导出 Invest 数据，或删除自选、持仓、事件与风测数据。SVQuant 账号本身的注销需在主站处理；公开版需提供完整注销通道、审计留存期限与响应时限。", "You can export Invest data or delete watchlist, holdings, event, and risk assessment data under “Me”. Deleting the SVQuant account itself must be handled on the main site; the public version must provide a complete deletion channel, audit retention periods, and response timeframes.")}</p>
      <h4>{t("4. 数据来源与延迟", "4. Data sources and delays")}</h4>
      <p>{t("行情、财务、估值来自腾讯/东方财富公开 EOD；公告、研报、要闻仅保留标题、来源、时间与原文链接；主题为成分股等权代理，不是官方指数。数据可能存在延迟、缺失或口径差异，以页面标注的数据日期为准。", "Quotes, financials, and valuation come from public EOD data provided by Tencent/East Money; filings, research reports, and news retain only the title, source, time, and original link; themes are equal-weight proxies of constituents, not official indices. Data may be delayed, missing, or defined differently—refer to the data date shown on the page.")}</p>
      <h4>{t("5. 安全", "5. Security")}</h4>
      <p>{t("我们使用 HTTPS、访问控制、最小权限与日志审计保护数据；审计记录可能包含 IP 与操作摘要。任何系统都无法保证绝对安全；如发生安全事件，将按适用法律通知受影响用户。", "We protect data with HTTPS, access controls, least privilege, and log auditing; audit records may include IP addresses and action summaries. No system can guarantee absolute security; if a security incident occurs, affected users will be notified as required by applicable law.")}</p>
      <h4>{t("6. 你的权利", "6. Your rights")}</h4>
      <p>{t("你可以请求访问、更正、导出或删除个人信息，或撤回同意。公开版需提供联系方式与处理流程；MVP 暂以页面说明代替。", "You may request access to, correction of, export of, or deletion of your personal information, or withdraw consent. The public version must provide contact details and a handling process; the MVP currently uses this page description instead.")}</p>
      <h4>{t("7. 未成年人", "7. Minors")}</h4>
      <p>{t("本产品面向具备完全民事行为能力的成年人；不面向未成年人提供投资相关信息服务。", "This product is intended for adults with full civil capacity; it does not provide investment-related information services to minors.")}</p>
      <h4>{t("8. 变更", "8. Changes")}</h4>
      <p>{t("政策更新会在页面公示；重大变更需重新取得同意。", "Policy updates will be posted on this page; material changes require renewed consent.")}</p>
    </LegalPage>
  );
}

export function Terms() {
  const { t } = useLocale();
  return (
    <LegalPage title={t("用户协议", "Terms of Service")} sub={t("草案 · 2026-10-26", "Draft · 2026-10-26")}>
      <h4>{t("1. 服务内容", "1. Service scope")}</h4>
      <p>{t("SVQuant Invest 提供收盘后的行情、财务、估值、组合体检、关注事件与资讯链接。所有内容为信息与教育用途，不构成投资建议、目标价或收益承诺。", "SVQuant Invest provides post-close quotes, financials, valuation, portfolio checkups, watch events, and news links. All content is for information and educational purposes and does not constitute investment advice, target prices, or return promises.")}</p>
      <h4>{t("2. 不提供交易服务", "2. No trading services")}</h4>
      <p>{t("本产品不接券商、不代客理财、不自动调仓、不执行交易。用户应独立判断并自行承担投资决策后果。", "This product does not connect to brokers, manage money for clients, rebalance automatically, or execute trades. Users must make independent judgments and bear the consequences of their investment decisions.")}</p>
      <h4>{t("3. 数据与延迟", "3. Data and delays")}</h4>
      <p>{t("行情、财务与资讯来自公开渠道，可能延迟、缺失或有误；页面会标注数据日期、来源与“非实时”。公告/研报/要闻仅提供标题与原文链接，不构成对原文的认可。用户不应将任何页面数据直接用于交易决策。", "Quotes, financials, and news come from public sources and may be delayed, missing, or inaccurate; pages label the data date, source, and “not real-time”. Filings/research/news provide only titles and original links and do not constitute endorsement of the original content. Users should not use any page data directly for trading decisions.")}</p>
      <h4>{t("4. 账号", "4. Accounts")}</h4>
      <p>{t("账号复用 SVQuant 账号体系；H5 为独立会话。用户应妥善保管密码，不得出借、转让或用于非法用途。注册代理已实现但默认关闭；找回密码、注销与风控规则以主站/公开版正式文本为准。", "Accounts use the SVQuant account system; H5 runs a separate session. Users must safeguard their passwords and must not lend, transfer, or use them for illegal purposes. The registration proxy is implemented but disabled by default; password recovery, account deletion, and risk-control rules are governed by the official text on the main site/public version.")}</p>
      <h4>{t("5. 禁止行为", "5. Prohibited conduct")}</h4>
      <p>{t("禁止爬取、批量导出、攻击、绕过限流、发布违法信息、利用本产品从事证券违法违规活动。", "Scraping, bulk export, attacks, bypassing rate limits, posting illegal information, and using this product for illegal securities activities are prohibited.")}</p>
      <h4>{t("6. 知识产权", "6. Intellectual property")}</h4>
      <p>{t("页面设计、规则与代码归平台所有；第三方数据与资讯归相应权利人所有，转载/商用需取得授权。", "Page design, rules, and code belong to the platform; third-party data and news belong to their respective rights holders, and reproduction/commercial use requires authorization.")}</p>
      <h4>{t("7. 责任限制", "7. Limitation of liability")}</h4>
      <p>{t("在法律允许范围内，平台不对因使用或无法使用本服务造成的投资损失、数据延迟或中断承担责任。", "To the extent permitted by law, the platform is not liable for investment losses, data delays, or interruptions caused by use of or inability to use this service.")}</p>
      <h4>{t("8. 变更与终止", "8. Changes and termination")}</h4>
      <p>{t("平台可基于合规、数据源或产品调整变更/终止服务，并提前公示。", "The platform may change or terminate the service due to compliance, data source, or product changes, with advance notice.")}</p>
      <h4>{t("9. 适用法律", "9. Governing law")}</h4>
      <p>{t("本协议适用中华人民共和国法律；争议解决方式以公开版正式文本为准。", "These terms are governed by the laws of the People's Republic of China; dispute resolution is governed by the official text of the public version.")}</p>
    </LegalPage>
  );
}
