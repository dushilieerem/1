import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useConfirm } from "@/components/ConfirmDialog";
import { PaperEquityChart } from "@/components/paper/PaperEquityChart";
import {
  getPaperAccount,
  getPaperStatus,
  listPaperAttempts,
  listPaperEquity,
  listPaperFills,
  listPaperOrders,
  listPaperPositions,
  listPaperSettlements,
  paperErrorLabel,
  paperErrorText,
  replayPaperAccount,
  settlePaperAccount,
  syncPaperStrategy,
  updatePaperAccount,
  type PaperAccount,
  type PaperAttempt,
  type PaperEquityPoint,
  type PaperFill,
  type PaperOrder,
  type PaperPosition,
  type PaperSettlement,
  type PaperStatus,
} from "@/lib/paperTradingApi";

const TABS = [
  { id: "overview", label: "概览" },
  { id: "positions", label: "持仓" },
  { id: "fills", label: "成交" },
  { id: "orders", label: "订单" },
  { id: "settlements", label: "结算记录" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function money(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  return `¥${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
}

function pct(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(2)}%`;
}

function dateTime(value?: string | null) {
  if (!value) return "—";
  return value.slice(0, 16).replace("T", " ");
}

const REASON_LABEL: Record<string, string> = {
  NO_VWAP: "无有效 VWAP",
  NO_PRICE: "无成交价",
  SUSPENDED: "停牌",
  LIMIT_UP: "涨停",
  LIMIT_DOWN: "跌停",
  T_PLUS_ONE: "T+1 不可卖",
  INSUFFICIENT_CASH: "现金不足",
  LOT_SIZE: "非整手",
  NO_POSITION: "无持仓变动",
  ST: "ST 限制",
  DELISTED: "退市",
};

const STATUS_LABEL: Record<string, string> = {
  active: "运行中",
  paused: "已暂停",
  closed: "已关闭",
  blocked: "需处理",
};

function statusClass(status: string) {
  if (status === "active") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (status === "paused") return "bg-amber-50 text-amber-700 border-amber-200";
  if (status === "blocked") return "bg-rose-50 text-rose-700 border-rose-200";
  return "bg-slate-100 text-slate-600 border-slate-200";
}

function StatCard({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <p className="text-[11px] text-slate-400">{label}</p>
      <p className={`mt-1 text-lg font-semibold tabular-nums ${tone || "text-slate-900"}`}>
        {value}
      </p>
    </div>
  );
}

export function PaperAccountPage() {
  const { accountId = "" } = useParams();
  const id = Number(accountId);
  const confirm = useConfirm();
  const [tab, setTab] = useState<TabId>("overview");
  const [account, setAccount] = useState<PaperAccount | null>(null);
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [equity, setEquity] = useState<PaperEquityPoint[]>([]);
  const [settlements, setSettlements] = useState<PaperSettlement[]>([]);
  const [orders, setOrders] = useState<PaperOrder[]>([]);
  const [fills, setFills] = useState<PaperFill[]>([]);
  const [attempts, setAttempts] = useState<PaperAttempt[]>([]);
  const [paperStatus, setPaperStatus] = useState<PaperStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () => {
    if (!Number.isFinite(id)) return;
    setLoading(true);
    setErr(null);
    void (async () => {
      try {
        const [
          detail,
          equityPoints,
          settlementData,
          orderData,
          fillData,
          attemptData,
          statusData,
        ] = await Promise.all([
          getPaperAccount(id),
          listPaperEquity(id),
          listPaperSettlements(id, { limit: 100 }),
          listPaperOrders(id, { limit: 300 }),
          listPaperFills(id, { limit: 300 }),
          listPaperAttempts(id),
          getPaperStatus().catch(() => null),
        ]);
        setAccount(detail.account);
        setPositions(detail.positions || []);
        setEquity(equityPoints);
        setSettlements(settlementData.settlements || []);
        setOrders(orderData.orders || []);
        setFills(fillData.fills || []);
        setAttempts(attemptData);
        setPaperStatus(statusData);
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    })();
  };

  useEffect(() => {
    refresh();
  }, [id]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 3000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const latestSettlement = settlements[0] || null;
  const latestAttempt = attempts[0] || null;
  const returnRate = useMemo(() => {
    if (!account || !account.initialCash) return null;
    return account.totalEquity / account.initialCash - 1;
  }, [account]);

  const settleNow = async () => {
    setBusy(true);
    setErr(null);
    try {
      const result = await settlePaperAccount(id);
      if (result.settled) setNotice("结算完成");
      else if (result.skipped === "not_trading_day") setNotice("非交易日，已推进到下一交易日");
      else setNotice("行情数据尚未就绪，稍后会自动重试");
      refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const toggleStatus = async () => {
    if (!account) return;
    const next = account.status === "paused" ? "active" : "paused";
    const ok = await confirm({
      title: next === "paused" ? "暂停账户" : "恢复账户",
      message:
        next === "paused"
          ? "暂停后不再自动结算，已有账本保留。"
          : "恢复后从下一未结算交易日继续补结算。",
    });
    if (!ok) return;
    setBusy(true);
    try {
      await updatePaperAccount(id, { status: next });
      refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const syncStrategy = async () => {
    const ok = await confirm({
      title: "同步策略",
      message:
        "将读取策略项目最新源码和参数并生成新的配置修订。若源码变化，已保存的策略状态会清空。",
      confirmLabel: "同步",
    });
    if (!ok) return;
    setBusy(true);
    try {
      await syncPaperStrategy(id);
      setNotice("策略快照已同步");
      refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const replayLatest = async () => {
    const ok = await confirm({
      title: "重算最新结算",
      message: "将回滚最新一笔结算并按当前行情 release 重新计算，仅在确认数据修复后使用。",
      confirmLabel: "回滚并重算",
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await replayPaperAccount(id);
      setNotice("最新结算已重算");
      refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading && !account) {
    return <div className="p-10 text-center text-sm text-slate-400">加载中…</div>;
  }

  if (!account) {
    return (
      <div className="p-10 text-center text-sm text-slate-500">
        {err || "账户不存在"} ·{" "}
        <Link to="/paper" className="text-blue-600">
          返回模拟盘
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-slate-50/80">
      <div className="mx-auto max-w-[1440px] px-4 py-6 lg:px-6 lg:py-8">
        <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm lg:p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <Link to="/paper" className="text-xs text-slate-400 hover:text-slate-700">
                ← 模拟盘
              </Link>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <h1 className="text-2xl font-semibold text-slate-900">{account.name}</h1>
                <span
                  className={`rounded-full border px-2 py-0.5 text-[11px] ${statusClass(account.status)}`}
                >
                  {STATUS_LABEL[account.status] || account.status}
                </span>
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-500">
                  {account.engineMode === "event" ? "事件策略" : "向量化"}
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {account.projectName} · {account.universe} · 基准 {account.benchmark} · 配置修订{" "}
                {account.configRevision}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                已结算至 {account.lastSettledDate || "尚未结算"} · 下次结算{" "}
                {account.nextSettlementDate}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy || account.status !== "active"}
                onClick={settleNow}
                className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
              >
                {busy ? "处理中…" : "立即结算"}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={toggleStatus}
                className="rounded-xl border border-slate-200 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                {account.status === "paused" ? "恢复" : "暂停"}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={syncStrategy}
                className="rounded-xl border border-slate-200 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                同步策略
              </button>
            </div>
          </div>

          {err ? (
            <p className="mt-3 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{err}</p>
          ) : null}
          {notice ? (
            <p className="mt-3 rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
              {notice}
            </p>
          ) : null}
          {account.lastErrorMessage ? (
            <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800">
              {paperErrorText(account.lastErrorCode, account.lastErrorMessage)}
              {account.nextRetryAt ? ` · 下次重试 ${dateTime(account.nextRetryAt)}` : ""}
            </p>
          ) : null}
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-500">
            <span>
              行情数据就绪至{" "}
              <b className="font-medium text-slate-700">
                {paperStatus?.re?.latest_ready_trading_day || "—"}
              </b>
            </span>
            <span>
              自动调度{" "}
              <b className="font-medium text-slate-700">
                {paperStatus?.scheduler?.enabled ? "开启" : "关闭"}
              </b>
            </span>
            <span>
              当前 release{" "}
              <b className="font-medium text-slate-700">
                {paperStatus?.re?.data_version || "—"}
              </b>
            </span>
            {paperStatus?.re?.release_stale ? (
              <span className="text-amber-700">行情 release 正在切换</span>
            ) : null}
          </div>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
          <StatCard label="总资产" value={money(account.totalEquity)} />
          <StatCard label="现金" value={money(account.cash)} />
          <StatCard label="持仓市值" value={money(account.positionsValue)} />
          <StatCard
            label="累计收益"
            value={pct(returnRate)}
            tone={(returnRate || 0) >= 0 ? "text-rose-600" : "text-emerald-600"}
          />
          <StatCard label="初始资金" value={money(account.initialCash)} />
        </div>

        <div className="mt-5 overflow-x-auto">
          <div className="flex min-w-max gap-1 rounded-2xl border border-slate-200/80 bg-white p-1 shadow-sm">
            {TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className={`rounded-xl px-4 py-2 text-sm transition ${
                  tab === item.id
                    ? "bg-slate-900 font-medium text-white"
                    : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        {tab === "overview" ? (
          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
            <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-800">资金曲线</h2>
              <PaperEquityChart equity={equity} />
            </div>
            <div className="space-y-4">
              <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
                <h2 className="text-sm font-semibold text-slate-800">最新结算</h2>
                {latestSettlement ? (
                  <dl className="mt-3 space-y-2 text-xs">
                    <div className="flex justify-between gap-3">
                      <dt className="text-slate-400">结算日</dt>
                      <dd className="text-slate-700">{latestSettlement.settlementDate}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-slate-400">信号日</dt>
                      <dd className="text-slate-700">{latestSettlement.signalDate}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-slate-400">收盘权益</dt>
                      <dd className="tabular-nums text-slate-700">
                        {money(latestSettlement.totalEquity)}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-slate-400">费用</dt>
                      <dd className="tabular-nums text-slate-700">
                        {money(latestSettlement.commission + latestSettlement.stampTax)}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-slate-400">行情 release</dt>
                      <dd className="max-w-[190px] truncate text-right text-slate-500">
                        {latestSettlement.dataReleaseId || "—"}
                      </dd>
                    </div>
                  </dl>
                ) : (
                  <p className="mt-3 text-xs text-slate-400">尚未结算</p>
                )}
              </div>

              <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
                <h2 className="text-sm font-semibold text-slate-800">最近结算尝试</h2>
                {latestAttempt ? (
                  <div className="mt-3 space-y-1 text-xs">
                    <p className="text-slate-700">
                      {latestAttempt.settlementDate} · {latestAttempt.status}
                    </p>
                    {latestAttempt.errorCode ? (
                      <>
                        <p className="text-rose-600">
                          {paperErrorText(
                            latestAttempt.errorCode,
                            latestAttempt.errorMessage,
                          )}
                        </p>
                        {paperErrorLabel(latestAttempt.errorCode) ? (
                          <p className="text-slate-400">
                            {latestAttempt.errorCode}: {latestAttempt.errorMessage}
                          </p>
                        ) : null}
                      </>
                    ) : null}
                    <p className="text-slate-400">
                      {dateTime(latestAttempt.startedAt)}
                      {latestAttempt.durationMs != null
                        ? ` · ${latestAttempt.durationMs} ms`
                        : ""}
                    </p>
                  </div>
                ) : (
                  <p className="mt-3 text-xs text-slate-400">暂无尝试记录</p>
                )}
              </div>
            </div>
          </div>
        ) : null}

        {tab === "positions" ? (
          <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3">证券</th>
                  <th className="px-4 py-3 text-right">持仓</th>
                  <th className="px-4 py-3 text-right">可卖</th>
                  <th className="px-4 py-3 text-right">平均成本</th>
                  <th className="px-4 py-3 text-right">最新价</th>
                  <th className="px-4 py-3 text-right">市值</th>
                  <th className="px-4 py-3 text-right">浮动盈亏</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {positions.length ? (
                  positions.map((item) => {
                    const pnl =
                      item.markPrice != null
                        ? (item.markPrice - item.averageCost) / item.averageCost
                        : null;
                    return (
                      <tr key={item.symbol}>
                        <td className="px-4 py-3 font-medium text-slate-800">{item.symbol}</td>
                        <td className="px-4 py-3 text-right tabular-nums">{item.quantity}</td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          {item.availableQuantity}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          {money(item.averageCost)}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          {money(item.markPrice)}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          {money(item.marketValue)}
                        </td>
                        <td
                          className={`px-4 py-3 text-right tabular-nums ${
                            (pnl || 0) >= 0 ? "text-rose-600" : "text-emerald-600"
                          }`}
                        >
                          {pct(pnl)}
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={7} className="px-4 py-10 text-center text-sm text-slate-400">
                      暂无持仓
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        ) : null}

        {tab === "fills" ? (
          <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3">结算日</th>
                  <th className="px-4 py-3">证券</th>
                  <th className="px-4 py-3">方向</th>
                  <th className="px-4 py-3 text-right">数量</th>
                  <th className="px-4 py-3 text-right">成交价</th>
                  <th className="px-4 py-3 text-right">佣金</th>
                  <th className="px-4 py-3 text-right">印花税</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {fills.length ? (
                  fills.map((fill) => (
                    <tr key={`${fill.settlementDate}-${fill.orderId}`}>
                      <td className="px-4 py-3 text-slate-600">{fill.settlementDate}</td>
                      <td className="px-4 py-3 font-medium text-slate-800">{fill.symbol}</td>
                      <td
                        className={`px-4 py-3 ${
                          fill.side === "buy" ? "text-rose-600" : "text-emerald-600"
                        }`}
                      >
                        {fill.side === "buy" ? "买入" : "卖出"}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">{fill.quantity}</td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {money(fill.price)}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {money(fill.commission)}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {money(fill.stampTax)}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7} className="px-4 py-10 text-center text-sm text-slate-400">
                      暂无成交
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        ) : null}

        {tab === "orders" ? (
          <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3">结算日</th>
                  <th className="px-4 py-3">证券</th>
                  <th className="px-4 py-3">方向</th>
                  <th className="px-4 py-3 text-right">目标数量/金额</th>
                  <th className="px-4 py-3">状态</th>
                  <th className="px-4 py-3">原因</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {orders.length ? (
                  orders.map((order) => (
                    <tr key={`${order.settlementDate}-${order.orderId}`}>
                      <td className="px-4 py-3 text-slate-600">{order.settlementDate}</td>
                      <td className="px-4 py-3 font-medium text-slate-800">{order.symbol}</td>
                      <td
                        className={`px-4 py-3 ${
                          order.side === "buy" ? "text-rose-600" : "text-emerald-600"
                        }`}
                      >
                        {order.side === "buy" ? "买入" : order.side === "sell" ? "卖出" : "—"}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {order.quantity != null
                          ? order.quantity
                          : order.targetValue != null
                            ? money(order.targetValue)
                            : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[11px] ${
                            order.status === "filled"
                              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                              : "border-slate-200 bg-slate-50 text-slate-500"
                          }`}
                        >
                          {order.status === "filled" ? "成交" : "拒单"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500">
                        {order.reasonCode
                          ? REASON_LABEL[order.reasonCode] || order.reasonCode
                          : "—"}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="px-4 py-10 text-center text-sm text-slate-400">
                      暂无订单
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        ) : null}

        {tab === "settlements" ? (
          <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
              <h2 className="text-sm font-semibold text-slate-800">结算记录</h2>
              {latestSettlement?.status === "applied" ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={replayLatest}
                  className="text-xs text-rose-600 hover:text-rose-700 disabled:opacity-50"
                >
                  回滚并重算最新结算
                </button>
              ) : null}
            </div>
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3">结算日</th>
                  <th className="px-4 py-3">信号日</th>
                  <th className="px-4 py-3">状态</th>
                  <th className="px-4 py-3 text-right">现金</th>
                  <th className="px-4 py-3 text-right">持仓市值</th>
                  <th className="px-4 py-3 text-right">总权益</th>
                  <th className="px-4 py-3 text-right">费用</th>
                  <th className="px-4 py-3">行情 release</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {settlements.length ? (
                  settlements.map((item) => (
                    <tr key={item.id}>
                      <td className="px-4 py-3 font-medium text-slate-800">
                        {item.settlementDate}
                      </td>
                      <td className="px-4 py-3 text-slate-600">{item.signalDate}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[11px] ${
                            item.status === "applied"
                              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                              : "border-slate-200 bg-slate-50 text-slate-500"
                          }`}
                        >
                          {item.status === "applied" ? "已结算" : "已回滚"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {money(item.cashAfter)}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {money(item.positionsValue)}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {money(item.totalEquity)}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {money(item.commission + item.stampTax)}
                      </td>
                      <td className="max-w-[220px] truncate px-4 py-3 text-xs text-slate-500">
                        {item.dataReleaseId || "—"}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={8} className="px-4 py-10 text-center text-sm text-slate-400">
                      暂无结算记录
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        ) : null}

        <p className="mt-4 text-xs leading-5 text-slate-400">
          成交价 = D 日成交额 / 成交量；估值使用 D 日未复权收盘价。当前版本不处理分红、送转、配股等公司行为。
        </p>
      </div>
    </div>
  );
}
