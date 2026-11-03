import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { humanizeEnum } from "../lib";
import { useLocale } from "../i18n";

const UNIVERSE_LABEL: Record<string, { zh: string; en: string }> = {
  CSI300: { zh: "沪深300", en: "CSI 300" },
  CSI500: { zh: "中证500", en: "CSI 500" },
};
const PERIOD_LABEL: Record<string, { zh: string; en: string }> = {
  "3m": { zh: "近3月", en: "3M" },
  "1y": { zh: "近1年", en: "1Y" },
  "3y": { zh: "近3年", en: "3Y" },
};

export default function QuantDashboard() {
  const nav = useNavigate();
  const { t } = useLocale();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [universe, setUniverse] = useState("CSI300");
  const [period, setPeriod] = useState("3y");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api<any>(`/api/factor/dashboard?universe=${universe}&period=${period}`)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [universe, period]);

  const rows = (data?.rows || []).slice().sort(
    (a: any, b: any) => Math.abs(Number(b.ic ?? 0)) - Math.abs(Number(a.ic ?? 0)),
  ).slice(0, 30);

  return (
    <div className="page">
      <PageHeader
        title={t("因子看板", "Factor Dashboard")}
        sub={t("IC/IR 来自平台回测缓存 · 非预测", "IC/IR from platform backtest cache · not a forecast")}
        back
        onBack={() => nav(-1)}
      />
      <div className="seg">
        {["CSI300", "CSI500"].map((x) => (
          <button key={x} className={universe === x ? "on" : ""} onClick={() => setUniverse(x)}>
            {t(UNIVERSE_LABEL[x].zh, UNIVERSE_LABEL[x].en)}
          </button>
        ))}
        {["3m", "1y", "3y"].map((x) => (
          <button key={x} className={period === x ? "on" : ""} onClick={() => setPeriod(x)}>
            {t(PERIOD_LABEL[x].zh, PERIOD_LABEL[x].en)}
          </button>
        ))}
      </div>
      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}
      {!loading && !rows.length ? (
        <EmptyState
          title={t("暂无面板指标", "No dashboard metrics yet")}
          detail={t("管理员刷新因子面板后会出现在这里。", "They will appear here after an admin refreshes the factor dashboard.")}
        />
      ) : null}
      {rows.length ? (
        <section className="card">
          <div className="card-title-row">
            <h2>{t(`${rows.length} 个因子`, `${rows.length} factors`)}</h2>
            <span className="hint">{t("按 |IC| 排序", "Sorted by |IC|")}</span>
          </div>
          <table className="data-table">
            <thead><tr><th>{t("因子", "Factor")}</th><th>IC</th><th>IR</th><th>{t("状态", "Status")}</th></tr></thead>
            <tbody>
              {rows.map((r: any) => (
                <tr key={`${r.library}-${r.factor_name}`}>
                  <td>{r.factor_name}</td>
                  <td>{r.ic == null ? t("待补充", "N/A") : Number(r.ic).toFixed(3)}</td>
                  <td>{r.ir == null ? t("待补充", "N/A") : Number(r.ir).toFixed(2)}</td>
                  <td><Tag tone={r.verify_status === "passed" ? "green" : r.verify_status === "failed" ? "red" : "gray"}>{humanizeEnum(r.verify_status || "pending")}</Tag></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint">
            {t(
              "IC = 因子与未来收益的相关性；IR = IC 的稳定性（IC / 波动）。平台口径缓存，不构成因子推荐。",
              "IC = correlation between the factor and future returns; IR = IC consistency (IC / volatility). Platform-defined cache, not a factor recommendation.",
            )}
          </p>
        </section>
      ) : null}
    </div>
  );
}
