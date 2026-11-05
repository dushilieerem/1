import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Disclaimer, EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { useLocale } from "../i18n";

type Constituent = { symbol: string; weight: number };
type Profile = {
  etf: string;
  tracking: string;
  tracked_index: string | null;
  constituent_count?: number;
  constituents: Constituent[];
  warning?: string;
};

const INDEX_NAME: Record<string, string> = {
  "000300.SH": "沪深300",
  "000905.SH": "中证500",
  "000016.SH": "上证50",
  "000852.SH": "中证1000",
  "000688.SH": "科创50",
  "399006.SZ": "创业板指",
};

type Overlap = {
  a: { etf: string; tracked_index: string | null };
  b: { etf: string; tracked_index: string | null };
  common_count: number;
  overlap_weight_pct: number;
  common: Array<{ symbol: string; a: number; b: number }>;
  warning?: string;
};

export default function EtfDetail() {
  const { t } = useLocale();
  const { code = "" } = useParams();
  const nav = useNavigate();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [other, setOther] = useState("");
  const [overlap, setOverlap] = useState<Overlap | null>(null);

  useEffect(() => {
    setLoading(true);
    api<Profile>(`/api/invest/etf/${code}`)
      .then(setProfile)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [code]);

  const compare = async () => {
    if (!other.trim()) return;
    try {
      const out = await api<Overlap>(
        `/api/invest/etf/overlap?a=${encodeURIComponent(code)}&b=${encodeURIComponent(other.trim())}`,
      );
      setOverlap(out);
    } catch (e: any) {
      setError(e.message || t("对比失败", "Comparison failed"));
    }
  };

  return (
    <div className="page">
      <PageHeader title={t("ETF 穿透", "ETF look-through")} sub={code} back onBack={() => nav(-1)} />
      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}

      {!loading && profile ? (
        <>
          <section className="card">
            <div className="card-title-row">
              <h2>{profile.etf.replace(/\.(SH|SZ)$/i, "")}</h2>
              <Tag tone={profile.tracking === "index_proxy" ? "amber" : "gray"}>
                {profile.tracking === "index_proxy"
                  ? t("指数代理", "Index proxy")
                  : profile.tracking === "cash_management"
                    ? t("货币 ETF", "Money-market ETF")
                    : t("未映射", "Unmapped")}
              </Tag>
            </div>
            <p className="hint">
              {t("跟踪指数", "Tracked index")}{t("：", ": ")}
              {profile.tracked_index
                ? `${INDEX_NAME[profile.tracked_index] || profile.tracked_index}${INDEX_NAME[profile.tracked_index] ? `（${profile.tracked_index}）` : ""}`
                : profile.tracking === "cash_management"
                  ? t("不适用（货币 ETF）", "N/A (money-market ETF)")
                  : "—"}
            </p>
            {profile.warning ? <div className="callout blue">{profile.warning}</div> : null}
          </section>

          {profile.constituents.length ? (
            <section className="card">
              <div className="card-title-row">
                <h2>{t(`成分（前 ${profile.constituents.length}）`, `Constituents (top ${profile.constituents.length})`)}</h2>
                <span className="hint">{t("权重 %", "Weight %")}</span>
              </div>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr><th>#</th><th>{t("代码", "Symbol")}</th><th>{t("权重", "Weight")}</th></tr>
                  </thead>
                  <tbody>
                    {profile.constituents.map((row, index) => (
                      <tr key={row.symbol}>
                        <td>{index + 1}</td>
                        <td>{row.symbol}</td>
                        <td>{row.weight.toFixed(3)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : (
            <EmptyState
              title={profile.tracking === "cash_management" ? t("货币 ETF 没有股票成分", "Money-market ETF has no equity constituents") : t("没有成分数据", "No constituent data")}
              detail={
                profile.tracking === "cash_management"
                  ? t("这是现金管理工具，不适用股票穿透；ETF 日线仅到 2026-10-23，不能当实时净值。", "This is a cash-management tool and is not subject to equity look-through; ETF daily data ends 2026-10-23 and is not a real-time NAV.")
                  : profile.tracked_index
                    ? t(
                        "跟踪指数已登记，但成分数据暂不可用；不按 0 处理。",
                        "The tracked index is registered, but constituent data is unavailable; not treated as zero.",
                      )
                    : t(
                        "该 ETF 尚未登记跟踪指数，需要补充官方持仓或映射。",
                        "This ETF has no tracked index yet; official holdings or a mapping need to be added.",
                      )
              }
            />
          )}

          <section className="card">
            <div className="card-title-row"><h2>{t("与另一只 ETF 对比", "Compare with another ETF")}</h2></div>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                value={other}
                onChange={(e) => setOther(e.target.value)}
                placeholder={t("另一只 ETF，如 510500", "Another ETF, e.g. 510500")}
                style={{ flex: 1, padding: 10, borderRadius: 10, border: "1px solid var(--line)", fontSize: 13 }}
              />
              <button className="btn btn-primary" disabled={!other.trim()} onClick={compare}>
                {t("对比", "Compare")}
              </button>
            </div>
            {overlap ? (
              <div className="hint" style={{ marginTop: 10 }}>
                {t("共同成分", "Common constituents")} {overlap.common_count} {t("只", "stocks")} · {t("加权重叠", "Weighted overlap")} {overlap.overlap_weight_pct.toFixed(2)}%
                {overlap.common.length ? t(`（${overlap.common.slice(0, 5).map((x) => x.symbol).join("、")}…）`, ` (${overlap.common.slice(0, 5).map((x) => x.symbol).join(", ")}…)`) : ""}
              </div>
            ) : null}
          </section>
        </>
      ) : null}

      <Disclaimer>{t("代理口径：以跟踪指数成分代替 ETF 官方持仓，不构成投资建议。", "Proxy basis: tracked-index constituents replace official ETF holdings; not investment advice.")}</Disclaimer>
    </div>
  );
}
