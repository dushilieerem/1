/**
 * 将 qlib_alpha 动态因子名展开为可放入策略类的方法源码（对齐 backend/factor/qlib_alpha.py）。
 * 策略 API 无 library_name，不能沿用 pass 存根。
 */

const EPSILON = "1e-12";
const WINDOWS = new Set([5, 10, 20, 30, 60]);

const KBAR: Record<string, string> = {
  kmid: "(self.close - self.open) / self.open",
  klen: "(self.high - self.low) / self.open",
  kmid2: `(self.close - self.open) / (self.high - self.low + ${EPSILON})`,
  kup: "(self.high - np.maximum(self.open, self.close)) / self.open",
  kup2: `(self.high - np.maximum(self.open, self.close)) / (self.high - self.low + ${EPSILON})`,
  klow: "(np.minimum(self.open, self.close) - self.low) / self.open",
  klow2: `(np.minimum(self.open, self.close) - self.low) / (self.high - self.low + ${EPSILON})`,
  ksft: "(2 * self.close - self.high - self.low) / self.open",
  ksft2: `(2 * self.close - self.high - self.low) / (self.high - self.low + ${EPSILON})`,
};

const FIELD0: Record<string, string> = {
  open: "self.open / self.close",
  high: "self.high / self.close",
  low: "self.low / self.close",
  vwap: "self._vwap() / self.close",
};

type Need = { vwap?: boolean; rolling?: boolean; np?: boolean };

function method(name: string, bodyLines: string[]): string {
  const body = bodyLines.map((l) => `    ${l}`).join("\n");
  return `def ${name}(self):\n${body}`;
}

function helpers(need: Need): string[] {
  const out: string[] = [];
  if (need.vwap) {
    out.push(
      [
        "def _vwap(self):",
        '    """优先 VWAP；缺失时用成交额/成交量。"""',
        '    if "vwap" in getattr(self, "fields", {}):',
        '        return self["vwap"]',
        `    return self.amount / (self.volume + ${EPSILON})`,
      ].join("\n"),
    );
  }
  if (need.rolling) {
    out.push(
      [
        "def _rolling_apply(self, frame, window, func):",
        "    return frame.rolling(window, min_periods=1).apply(func, raw=True)",
      ].join("\n"),
    );
  }
  return out;
}

function expandAlpha360(name: string): { code: string; need: Need } | null {
  const m = /^qlib_alpha360_(close|open|high|low|vwap|volume)(\d+)$/.exec(name);
  if (!m) return null;
  const field = m[1];
  const day = Number(m[2]);
  if (!Number.isFinite(day) || day < 0 || day > 59) return null;
  const need: Need = { np: true };
  let expr: string;
  if (field === "volume") {
    expr = `self.volume.shift(${day}) / (self.volume + ${EPSILON})`;
  } else if (field === "vwap") {
    need.vwap = true;
    expr = `self._vwap().shift(${day}) / self.close`;
  } else {
    expr = `self.${field}.shift(${day}) / self.close`;
  }
  return {
    need,
    code: method(name, [
      '"""Qlib Alpha360 特征（社区克隆展开）。"""',
      "import numpy as np  # noqa: F401",
      `return ${expr}`,
    ]),
  };
}

function expandAlpha158(name: string): { code: string; need: Need } | null {
  const need: Need = { np: true };
  const kbar = /^qlib_alpha158_(kmid2?|klen|kup2?|klow2?|ksft2?)$/.exec(name);
  if (kbar) {
    const key = kbar[1];
    const expr = KBAR[key];
    if (!expr) return null;
    return {
      need,
      code: method(name, [
        '"""Qlib Alpha158 K线特征（社区克隆展开）。"""',
        "import numpy as np",
        `return ${expr}`,
      ]),
    };
  }

  const f0 = /^qlib_alpha158_(open|high|low|vwap)0$/.exec(name);
  if (f0) {
    const key = f0[1];
    if (key === "vwap") need.vwap = true;
    return {
      need,
      code: method(name, [
        '"""Qlib Alpha158 相对收盘价（社区克隆展开）。"""',
        "import numpy as np  # noqa: F401",
        `return ${FIELD0[key]}`,
      ]),
    };
  }

  const roll = /^qlib_alpha158_([a-z]+)(5|10|20|30|60)$/.exec(name);
  if (!roll) return null;
  const suffix = roll[1];
  const window = Number(roll[2]);
  if (!WINDOWS.has(window)) return null;

  const R = `self.close.rolling(${window}, min_periods=1)`;
  const Rh = `self.high.rolling(${window}, min_periods=1)`;
  const Rl = `self.low.rolling(${window}, min_periods=1)`;
  const Rv = `self.volume.rolling(${window}, min_periods=1)`;

  const simple: Record<string, string> = {
    roc: `self.close.shift(${window}) / self.close`,
    ma: `${R}.mean() / self.close`,
    std: `${R}.std() / self.close`,
    max: `${Rh}.max() / self.close`,
    min: `${Rl}.min() / self.close`,
    qtlu: `${R}.quantile(0.8) / self.close`,
    qtld: `${R}.quantile(0.2) / self.close`,
    rank: `${R}.rank(pct=True)`,
    rsv: `(self.close - ${Rl}.min()) / (${Rh}.max() - ${Rl}.min() + ${EPSILON})`,
    corr: `${R}.corr(np.log(self.volume + 1))`,
    cord: `(self.close / self.close.shift(1)).rolling(${window}, min_periods=1).corr(np.log(self.volume / self.volume.shift(1) + 1))`,
    cntp: `((self.close - self.close.shift(1)) > 0).astype(float).rolling(${window}, min_periods=1).mean()`,
    cntn: `((self.close - self.close.shift(1)) < 0).astype(float).rolling(${window}, min_periods=1).mean()`,
    cntd: `((self.close - self.close.shift(1)) > 0).astype(float).rolling(${window}, min_periods=1).mean() - ((self.close - self.close.shift(1)) < 0).astype(float).rolling(${window}, min_periods=1).mean()`,
    sump: `(self.close - self.close.shift(1)).clip(lower=0).rolling(${window}, min_periods=1).sum() / ((self.close - self.close.shift(1)).abs().rolling(${window}, min_periods=1).sum() + ${EPSILON})`,
    sumn: `(-(self.close - self.close.shift(1))).clip(lower=0).rolling(${window}, min_periods=1).sum() / ((self.close - self.close.shift(1)).abs().rolling(${window}, min_periods=1).sum() + ${EPSILON})`,
    sumd: `((self.close - self.close.shift(1)).clip(lower=0).rolling(${window}, min_periods=1).sum() - (-(self.close - self.close.shift(1))).clip(lower=0).rolling(${window}, min_periods=1).sum()) / ((self.close - self.close.shift(1)).abs().rolling(${window}, min_periods=1).sum() + ${EPSILON})`,
    vma: `${Rv}.mean() / (self.volume + ${EPSILON})`,
    vstd: `${Rv}.std() / (self.volume + ${EPSILON})`,
    wvma: `((self.close / self.close.shift(1) - 1).abs() * self.volume).rolling(${window}, min_periods=1).std() / (((self.close / self.close.shift(1) - 1).abs() * self.volume).rolling(${window}, min_periods=1).mean() + ${EPSILON})`,
    vsump: `(self.volume - self.volume.shift(1)).clip(lower=0).rolling(${window}, min_periods=1).sum() / ((self.volume - self.volume.shift(1)).abs().rolling(${window}, min_periods=1).sum() + ${EPSILON})`,
    vsumn: `(-(self.volume - self.volume.shift(1))).clip(lower=0).rolling(${window}, min_periods=1).sum() / ((self.volume - self.volume.shift(1)).abs().rolling(${window}, min_periods=1).sum() + ${EPSILON})`,
    vsumd: `((self.volume - self.volume.shift(1)).clip(lower=0).rolling(${window}, min_periods=1).sum() - (-(self.volume - self.volume.shift(1))).clip(lower=0).rolling(${window}, min_periods=1).sum()) / ((self.volume - self.volume.shift(1)).abs().rolling(${window}, min_periods=1).sum() + ${EPSILON})`,
  };

  if (simple[suffix]) {
    return {
      need,
      code: method(name, [
        `"""Qlib Alpha158 ${suffix.toUpperCase()}${window}（社区克隆展开）。"""`,
        "import numpy as np",
        `return ${simple[suffix]}`,
      ]),
    };
  }

  // beta / rsqr / resi / imax / imin / imxd → _rolling_apply
  need.rolling = true;
  const applyMap: Record<string, string[]> = {
    beta: [
      "import numpy as np",
      "def _linear_slope(values):",
      "    if len(values) < 2 or not np.isfinite(values).all():",
      "        return np.nan",
      "    return float(np.polyfit(np.arange(len(values)), values, 1)[0])",
      `return self._rolling_apply(self.close, ${window}, _linear_slope) / self.close`,
    ],
    rsqr: [
      "import numpy as np",
      "def _linear_rsquare(values):",
      "    if len(values) < 2 or not np.isfinite(values).all() or np.std(values) <= 2e-5:",
      "        return np.nan",
      "    return float(np.corrcoef(np.arange(len(values)), values)[0, 1] ** 2)",
      `return self._rolling_apply(self.close, ${window}, _linear_rsquare)`,
    ],
    resi: [
      "import numpy as np",
      "def _linear_residual(values):",
      "    if len(values) < 2 or not np.isfinite(values).all():",
      "        return np.nan",
      "    return float(values[-1] - np.polyval(np.polyfit(np.arange(len(values)), values, 1), len(values) - 1))",
      `return self._rolling_apply(self.close, ${window}, _linear_residual) / self.close`,
    ],
    imax: [
      "import numpy as np",
      `return self._rolling_apply(self.high, ${window}, lambda x: np.argmax(x) + 1) / ${window}`,
    ],
    imin: [
      "import numpy as np",
      `return self._rolling_apply(self.low, ${window}, lambda x: np.argmin(x) + 1) / ${window}`,
    ],
    imxd: [
      "import numpy as np",
      `return (self._rolling_apply(self.high, ${window}, lambda x: np.argmax(x) + 1) - self._rolling_apply(self.low, ${window}, lambda x: np.argmin(x) + 1)) / ${window}`,
    ],
  };
  const lines = applyMap[suffix];
  if (!lines) return null;
  return {
    need,
    code: method(name, [
      `"""Qlib Alpha158 ${suffix.toUpperCase()}${window}（社区克隆展开）。"""`,
      ...lines,
    ]),
  };
}

/** 成功返回可 wrap 进策略的方法源码（可含 _vwap / _rolling_apply）；失败返回 null */
export function expandQlibAlphaFactorSource(factorName: string): string | null {
  const name = (factorName || "").trim();
  if (!name.startsWith("qlib_alpha")) return null;
  const hit = expandAlpha360(name) || expandAlpha158(name);
  if (!hit) return null;
  const parts = [...helpers(hit.need), hit.code];
  return parts.join("\n\n");
}

export function isQlibAlphaFactorName(name: string): boolean {
  return /^qlib_alpha(158|360)_/.test((name || "").trim());
}
