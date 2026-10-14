/**
 * 回测交易过滤开关组：停牌 / ST / 涨停 / 跌停。
 *
 * 字段名与服务端（ResearchEngine）请求字段一致，便于直接展开进请求体。
 */

export type BacktestFilterKey =
  | "filter_suspended"
  | "filter_st"
  | "filter_limit_up"
  | "filter_limit_down";

export type BacktestFilterValues = Record<BacktestFilterKey, boolean>;

/** 展示顺序与后端文档一致。 */
export const BACKTEST_FILTER_TOGGLES: ReadonlyArray<{
  key: BacktestFilterKey;
  label: string;
}> = [
  { key: "filter_suspended", label: "过滤停牌" },
  { key: "filter_st", label: "过滤ST" },
  { key: "filter_limit_up", label: "过滤涨停" },
  { key: "filter_limit_down", label: "过滤跌停" },
];

/**
 * 事件模式的撮合层会无条件拒掉停牌单、涨停买入单与跌停卖出单，
 * 因此这三个开关在服务端不额外生效，界面上置灰。
 */
const EVENT_FORCED: ReadonlyArray<BacktestFilterKey> = [
  "filter_suspended",
  "filter_limit_up",
  "filter_limit_down",
];

export function BacktestFilterToggles(props: {
  value: BacktestFilterValues;
  engineMode: "vectorized" | "event";
  onChange: (patch: Partial<BacktestFilterValues>) => void;
}) {
  const { value, engineMode, onChange } = props;
  const isEvent = engineMode === "event";

  return (
    <section className="mt-3 rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2.5">
      <div className="text-xs font-medium text-slate-700">交易过滤</div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
        {BACKTEST_FILTER_TOGGLES.map(({ key, label }) => {
          const disabled = isEvent && EVENT_FORCED.includes(key);
          return (
            <label
              key={key}
              className={`flex items-center gap-2 text-xs text-slate-600 ${
                disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"
              }`}
            >
              <input
                type="checkbox"
                className="h-3.5 w-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-200"
                checked={value[key]}
                disabled={disabled}
                onChange={(e) => {
                  // 置灰时仍保留并上报用户原有的取值：切回向量化模式后设置不丢。
                  const patch: Partial<BacktestFilterValues> = {};
                  patch[key] = e.target.checked;
                  onChange(patch);
                }}
              />
              {label}
            </label>
          );
        })}
      </div>
      {isEvent ? (
        <p className="mt-1 text-[11px] leading-snug text-slate-400">
          事件模式由撮合层强制拦截，无需设置
        </p>
      ) : null}
    </section>
  );
}
