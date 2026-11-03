/**
 * E2E 写库闸门：默认只读；写库必须同时满足人工开关与服务端真实库名校验。
 *
 * - allowWrite（INST_E2E_ALLOW_WRITE=1）只是人工开关，不能自证目标库；
 * - guardResponse 必须来自服务端 GET /api/inst/_e2e/guard，含真实 db_name；
 * - 只有 db_name 含 _test / _e2e 且服务端 writable=true 才 enabled；
 * - 端点不可达、返回空、库名缺失、库名是生产库，全部 fatal（fail fast）。
 * - expectDb（可选 INST_E2E_EXPECT_DB）用于比对服务端返回的精确库名。
 */
export function evaluateWriteGuard({ allowWrite = false, guardResponse = null, expectDb = "" } = {}) {
  if (!allowWrite) return { enabled: false, fatal: null, dbName: null };
  if (!guardResponse || typeof guardResponse !== "object") {
    return {
      enabled: false,
      fatal: "无法读取服务端 E2E guard（端点不可达或返回为空），拒绝写库。",
      dbName: null,
    };
  }
  if (guardResponse.error) {
    return {
      enabled: false,
      fatal: `无法读取服务端 E2E guard（${guardResponse.error}），拒绝写库。`,
      dbName: null,
    };
  }
  const dbName = String(guardResponse.db_name || "").trim();
  if (!dbName) {
    return {
      enabled: false,
      fatal: "服务端 E2E guard 未返回 db_name，拒绝写库。",
      dbName: null,
    };
  }
  const nameSafe = dbName.includes("_test") || dbName.includes("_e2e");
  if (!nameSafe) {
    return {
      enabled: false,
      fatal: `目标库 ${dbName} 不是独立测试库（库名需含 _test/_e2e），拒绝写库。`,
      dbName,
    };
  }
  if (guardResponse.writable !== true) {
    return {
      enabled: false,
      fatal: `服务端判定目标库 ${dbName} 不可写，拒绝写库。`,
      dbName,
    };
  }
  const expected = String(expectDb || "").trim();
  if (expected && expected !== dbName) {
    return {
      enabled: false,
      fatal: `目标库 ${dbName} 与 INST_E2E_EXPECT_DB=${expected} 不一致，拒绝写库。`,
      dbName,
    };
  }
  return { enabled: true, fatal: null, dbName };
}
