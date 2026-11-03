/**
 * E2E 写库闸门：默认只读；写库必须显式声明目标是独立测试库。
 *
 * - INST_E2E_ALLOW_WRITE=1 才考虑写库；
 * - INST_E2E_DB 必须为 safe，或库名含 _test / _e2e；
 * - 只设 ALLOW_WRITE 而目标不安全时返回 fatal，由用例 fail fast，不能静默 skip。
 */
export function evaluateWriteGuard(env = process.env) {
  const allow = String(env.INST_E2E_ALLOW_WRITE || "").trim() === "1";
  const tag = String(env.INST_E2E_DB || "").trim().toLowerCase();
  const safe = tag === "safe" || tag.includes("_test") || tag.includes("_e2e");
  if (allow && !safe) {
    return {
      enabled: false,
      fatal:
        "拒绝写库 E2E：INST_E2E_ALLOW_WRITE=1 时必须同时设置 INST_E2E_DB=safe（或库名含 _test/_e2e）；禁止指向生产库 svquant。",
    };
  }
  return { enabled: allow && safe, fatal: null };
}
