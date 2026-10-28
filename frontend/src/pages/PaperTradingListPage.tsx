import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useConfirm } from "@/components/ConfirmDialog";
import {
  createPaperAccount,
  listPaperAccounts,
  paperErrorText,
  settlePaperAccount,
  updatePaperAccount,
  type PaperAccount,
} from "@/lib/paperTradingApi";
import {
  listStrategyProjects,
  type StrategyProject,
} from "@/lib/strategyStore";

function money(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  return `¥${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
}

function pct(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(2)}%`;
}

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

export function PaperTradingListPage() {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [projects, setProjects] = useState<StrategyProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createProject, setCreateProject] = useState("");
  const [createCash, setCreateCash] = useState("1000000");
  const [createDate, setCreateDate] = useState("");
  const [createErr, setCreateErr] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const refresh = () => {
    setLoading(true);
    setErr(null);
    void (async () => {
      try {
        const [list, projectList] = await Promise.all([
          listPaperAccounts(),
          listStrategyProjects().catch(() => []),
        ]);
        setAccounts(list);
        setProjects(projectList);
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    })();
  };

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 3000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === createProject) || null,
    [projects, createProject],
  );

  const openCreate = () => {
    setCreateName("");
    setCreateProject(projects[0]?.id || "");
    const capital = projects[0]?.config?.initial_capital;
    setCreateCash(String(typeof capital === "number" && capital > 0 ? capital : 1000000));
    setCreateDate("");
    setCreateErr(null);
    setCreateOpen(true);
  };

  const submitCreate = async () => {
    if (!createProject) {
      setCreateErr("请选择策略项目");
      return;
    }
    const cash = Number(createCash);
    if (!Number.isFinite(cash) || cash <= 0) {
      setCreateErr("初始资金必须大于 0");
      return;
    }
    setCreating(true);
    setCreateErr(null);
    try {
      const account = await createPaperAccount({
        name: createName.trim() || selectedProject?.name || "模拟账户",
        strategy_project_id: createProject,
        initial_cash: cash,
        first_settlement_date: createDate || undefined,
      });
      setCreateOpen(false);
      setNotice("模拟账户已创建");
      navigate(`/paper/${account.id}`);
    } catch (e) {
      setCreateErr(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  };

  const toggleStatus = async (account: PaperAccount) => {
    const next = account.status === "paused" ? "active" : "paused";
    const ok = await confirm({
      title: next === "paused" ? "暂停账户" : "恢复账户",
      message:
        next === "paused"
          ? "暂停后日终调度不会再结算该账户，已有账本保留。"
          : "恢复后将从下一未结算交易日继续补结算。",
      confirmLabel: next === "paused" ? "暂停" : "恢复",
    });
    if (!ok) return;
    setBusy(account.id);
    try {
      await updatePaperAccount(account.id, { status: next });
      setNotice(next === "paused" ? "账户已暂停" : "账户已恢复");
      refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const settleNow = async (account: PaperAccount) => {
    setBusy(account.id);
    setErr(null);
    try {
      const result = await settlePaperAccount(account.id);
      if (result.settled) setNotice("结算完成");
      else if (result.skipped === "not_trading_day") setNotice("非交易日，已推进到下一交易日");
      else setNotice("行情数据尚未就绪，稍后会自动重试");
      refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const closeAccount = async (account: PaperAccount) => {
    const ok = await confirm({
      title: "关闭账户",
      message: "关闭后不再结算；账本与成交记录保留。确定关闭？",
      confirmLabel: "关闭账户",
      danger: true,
    });
    if (!ok) return;
    setBusy(account.id);
    try {
      await updatePaperAccount(account.id, { status: "closed" });
      setNotice("账户已关闭");
      refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-slate-50/80">
      <div className="mx-auto max-w-[1440px] px-4 py-6 lg:px-6 lg:py-8">
        <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm lg:p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">
                Paper Trading
              </p>
              <h1 className="mt-1 text-2xl font-semibold text-slate-900">模拟盘</h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
                账户绑定策略项目快照。每个交易日收盘后使用 D-1 数据生成信号，
                按 D 日成交额/成交量的 VWAP 全量成交，并以未复权收盘价估值。
              </p>
            </div>
            <button
              type="button"
              onClick={openCreate}
              className="inline-flex items-center justify-center rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-700"
            >
              新建模拟账户
            </button>
          </div>
          {err ? (
            <p className="mt-3 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {err}
            </p>
          ) : null}
          {notice ? (
            <p className="mt-3 rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
              {notice}
            </p>
          ) : null}
        </div>

        <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3 lg:px-5">
            <h2 className="text-sm font-semibold text-slate-800">
              我的账户{" "}
              <span className="ml-1 font-normal text-slate-400">{accounts.length}</span>
            </h2>
            <button
              type="button"
              onClick={refresh}
              className="text-xs text-slate-500 hover:text-slate-800"
            >
              刷新
            </button>
          </div>

          {loading ? (
            <div className="p-10 text-center text-sm text-slate-400">加载中…</div>
          ) : !accounts.length ? (
            <div className="p-12 text-center">
              <p className="text-sm text-slate-500">还没有模拟账户</p>
              <button
                type="button"
                onClick={openCreate}
                className="mt-3 text-sm font-medium text-blue-600 hover:text-blue-700"
              >
                用已有策略项目创建一个
              </button>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {accounts.map((account) => {
                const ret =
                  account.initialCash > 0
                    ? account.totalEquity / account.initialCash - 1
                    : null;
                return (
                  <div
                    key={account.id}
                    className="flex flex-col gap-4 px-4 py-4 lg:flex-row lg:items-center lg:px-5"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link
                          to={`/paper/${account.id}`}
                          className="truncate text-base font-semibold text-slate-900 hover:text-blue-600"
                        >
                          {account.name}
                        </Link>
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[11px] ${statusClass(account.status)}`}
                        >
                          {STATUS_LABEL[account.status] || account.status}
                        </span>
                        <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-500">
                          {account.engineMode === "event" ? "事件策略" : "向量化"}
                        </span>
                      </div>
                      <p className="mt-1 truncate text-xs text-slate-500">
                        {account.projectName} · {account.universe} · 下次结算{" "}
                        {account.nextSettlementDate}
                        {account.lastSettledDate
                          ? ` · 已结算至 ${account.lastSettledDate}`
                          : " · 尚未结算"}
                      </p>
                      {account.lastErrorMessage ? (
                        <p className="mt-1 text-xs text-rose-600">
                          {paperErrorText(
                            account.lastErrorCode,
                            account.lastErrorMessage,
                          )}
                        </p>
                      ) : null}
                    </div>

                    <div className="grid grid-cols-3 gap-4 text-right lg:w-[360px]">
                      <div>
                        <p className="text-[11px] text-slate-400">总资产</p>
                        <p className="mt-0.5 text-sm font-semibold tabular-nums text-slate-900">
                          {money(account.totalEquity)}
                        </p>
                      </div>
                      <div>
                        <p className="text-[11px] text-slate-400">现金</p>
                        <p className="mt-0.5 text-sm tabular-nums text-slate-700">
                          {money(account.cash)}
                        </p>
                      </div>
                      <div>
                        <p className="text-[11px] text-slate-400">累计收益</p>
                        <p
                          className={`mt-0.5 text-sm font-semibold tabular-nums ${
                            (ret || 0) >= 0 ? "text-rose-600" : "text-emerald-600"
                          }`}
                        >
                          {pct(ret)}
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 lg:w-[250px] lg:justify-end">
                      <button
                        type="button"
                        disabled={busy === account.id || account.status === "closed"}
                        onClick={() => settleNow(account)}
                        className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                      >
                        立即结算
                      </button>
                      {account.status !== "closed" ? (
                        <button
                          type="button"
                          disabled={busy === account.id}
                          onClick={() => toggleStatus(account)}
                          className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                        >
                          {account.status === "paused" ? "恢复" : "暂停"}
                        </button>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => navigate(`/paper/${account.id}`)}
                        className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                      >
                        详情
                      </button>
                      {account.status !== "closed" ? (
                        <button
                          type="button"
                          disabled={busy === account.id}
                          onClick={() => closeAccount(account)}
                          className="rounded-lg px-2 py-1.5 text-xs text-slate-400 hover:text-rose-600 disabled:opacity-50"
                        >
                          关闭
                        </button>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <p className="mt-4 text-xs leading-5 text-slate-400">
          当前版本不处理分红、送转、配股等公司行为；跨公司行为日期的模拟结果不作准确性保证。
          首期只支持现金多头、整手、T+1 和全量成交。
        </p>
      </div>

      {createOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-5 shadow-xl">
            <h3 className="text-lg font-semibold text-slate-900">新建模拟账户</h3>
            <p className="mt-1 text-xs text-slate-500">
              创建时快照策略源码、执行模式、股票池和费用；项目后续修改不会自动影响账户。
            </p>

            <div className="mt-4 space-y-3">
              <label className="block">
                <span className="text-xs font-medium text-slate-600">策略项目</span>
                <select
                  value={createProject}
                  onChange={(event) => {
                    const id = event.target.value;
                    setCreateProject(id);
                    const project = projects.find((item) => item.id === id);
                    const capital = project?.config?.initial_capital;
                    if (typeof capital === "number" && capital > 0) {
                      setCreateCash(String(capital));
                    }
                  }}
                  className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
                >
                  {!projects.length ? <option value="">暂无可选策略项目</option> : null}
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                      {project.config?.engine_mode === "event" ? "（事件）" : "（向量化）"}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="text-xs font-medium text-slate-600">账户名称</span>
                <input
                  value={createName}
                  onChange={(event) => setCreateName(event.target.value)}
                  placeholder={selectedProject?.name || "模拟账户"}
                  className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
                />
              </label>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="block">
                  <span className="text-xs font-medium text-slate-600">初始资金</span>
                  <input
                    type="number"
                    min={1}
                    value={createCash}
                    onChange={(event) => setCreateCash(event.target.value)}
                    className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
                  />
                </label>
                <label className="block">
                  <span className="text-xs font-medium text-slate-600">
                    首个结算日（可选）
                  </span>
                  <input
                    type="date"
                    value={createDate}
                    onChange={(event) => setCreateDate(event.target.value)}
                    className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
                  />
                </label>
              </div>
              <p className="text-[11px] text-slate-400">
                留空时：收盘前创建从当天开始，收盘后创建从下一交易日开始。显式填写可用于补历史联调，不能晚于今天。
              </p>
            </div>

            {createErr ? (
              <p className="mt-3 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {createErr}
              </p>
            ) : null}

            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setCreateOpen(false)}
                className="rounded-xl border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                取消
              </button>
              <button
                type="button"
                disabled={creating}
                onClick={submitCreate}
                className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
              >
                {creating ? "创建中…" : "创建"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
