import { Link } from "react-router-dom";
import { Calculator, Gauge, History, LineChart, ListChecks, Radio, Trophy } from "lucide-react";
import { PageHeader } from "../components";
import { useLocale } from "../i18n";

export default function Quant() {
  const { t } = useLocale();
  return (
    <div className="page">
      <PageHeader
        title={t("量化研究", "Quant Research")}
        sub={t("因子库与策略库只读浏览 · 完整回测在桌面端", "Read-only factor and strategy libraries · Full backtests on desktop")}
      />
      <div className="post-list">
        <Link to="/quant/factor" className="post-row">
          <div className="post-row-title">
            <Calculator size={14} style={{ marginRight: 6 }} /> {t("因子库", "Factor Library")}
          </div>
          <div className="hint">{t("查看已入库因子、所属库与说明。", "View registered factors, their library, and descriptions.")}</div>
        </Link>
        <Link to="/quant/strategy" className="post-row">
          <div className="post-row-title">
            <LineChart size={14} style={{ marginRight: 6 }} /> {t("策略库", "Strategy Library")}
          </div>
          <div className="hint">{t("浏览内置经典策略与版本信息。", "Browse built-in classic strategies and version info.")}</div>
        </Link>
        <Link to="/quant/dashboard" className="post-row">
          <div className="post-row-title"><Gauge size={14} style={{ marginRight: 6 }} /> {t("因子看板", "Factor Dashboard")}</div>
          <div className="hint">{t("查看平台因子 IC/IR 与校验状态。", "View platform factor IC/IR and validation status.")}</div>
        </Link>
        <Link to="/quant/select" className="post-row">
          <div className="post-row-title"><ListChecks size={14} style={{ marginRight: 6 }} /> {t("轻量因子选股", "Lightweight Factor Screening")}</div>
          <div className="hint">{t("低估值、高股息与 20 日动量的规则打分。", "Rule-based scoring on low valuation, high dividend yield, and 20-day momentum.")}</div>
        </Link>
        <Link to="/quant/signals" className="post-row">
          <div className="post-row-title"><Radio size={14} style={{ marginRight: 6 }} /> {t("策略信号", "Strategy Signals")}</div>
          <div className="hint">{t("模拟盘最新持仓与现金，不是交易指令。", "Latest paper-trading positions and cash — not trading instructions.")}</div>
        </Link>
        <Link to="/quant/backtests" className="post-row">
          <div className="post-row-title"><History size={14} style={{ marginRight: 6 }} /> {t("回测速览", "Backtest Overview")}</div>
          <div className="hint">{t("只读网页端回测：指标、净值曲线与 AI 解读。", "Read-only web backtests: metrics, equity curve, and AI commentary.")}</div>
        </Link>
        <Link to="/quant/plaza" className="post-row">
          <div className="post-row-title"><Trophy size={14} style={{ marginRight: 6 }} /> {t("策略广场", "Strategy Plaza")}</div>
          <div className="hint">{t("社区公开策略快照与收益/回撤排序。", "Community strategy snapshots ranked by return/drawdown.")}</div>
        </Link>
      </div>
    </div>
  );
}
