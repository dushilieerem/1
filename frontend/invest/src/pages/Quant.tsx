import { Link } from "react-router-dom";
import { Calculator, Gauge, History, LineChart, ListChecks, Radio, Trophy } from "lucide-react";
import { PageHeader } from "../components";

export default function Quant() {
  return (
    <div className="page">
      <PageHeader title="量化研究" sub="因子库与策略库只读浏览 · 完整回测在桌面端" />
      <div className="post-list">
        <Link to="/quant/factor" className="post-row">
          <div className="post-row-title">
            <Calculator size={14} style={{ marginRight: 6 }} /> 因子库
          </div>
          <div className="hint">查看已入库因子、所属库与说明。</div>
        </Link>
        <Link to="/quant/strategy" className="post-row">
          <div className="post-row-title">
            <LineChart size={14} style={{ marginRight: 6 }} /> 策略库
          </div>
          <div className="hint">浏览内置经典策略与版本信息。</div>
        </Link>
        <Link to="/quant/dashboard" className="post-row">
          <div className="post-row-title"><Gauge size={14} style={{ marginRight: 6 }} /> 因子看板</div>
          <div className="hint">查看平台因子 IC/IR 与校验状态。</div>
        </Link>
        <Link to="/quant/select" className="post-row">
          <div className="post-row-title"><ListChecks size={14} style={{ marginRight: 6 }} /> 轻量因子选股</div>
          <div className="hint">低估值、高股息与 20 日动量的规则打分。</div>
        </Link>
        <Link to="/quant/signals" className="post-row">
          <div className="post-row-title"><Radio size={14} style={{ marginRight: 6 }} /> 策略信号</div>
          <div className="hint">模拟盘最新持仓与现金，不是交易指令。</div>
        </Link>
        <Link to="/quant/backtests" className="post-row">
          <div className="post-row-title"><History size={14} style={{ marginRight: 6 }} /> 回测速览</div>
          <div className="hint">只读网页端回测：指标、净值曲线与 AI 解读。</div>
        </Link>
        <Link to="/quant/plaza" className="post-row">
          <div className="post-row-title"><Trophy size={14} style={{ marginRight: 6 }} /> 策略广场</div>
          <div className="hint">社区公开策略快照与收益/回撤排序。</div>
        </Link>
      </div>
    </div>
  );
}
