import { Link } from "react-router-dom";
import { Calculator, LineChart } from "lucide-react";
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
      </div>
    </div>
  );
}
