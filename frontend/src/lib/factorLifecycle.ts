/**
 * 因子库 ↔ 检测 生命周期用例（Application 层）。
 * 页面只编排 UI，建空因子 / 打开检测 / 成功回写 / 全局报告 走这里。
 */
import type { FactorMeta } from "./factorCatalog";
import {
  openOrCreateForFactor,
  openDetectPlaceholderTab,
  navigateDetectTab,
  listAllDetectRuns,
  updateDetectRunRemark,
  updateDetectRunFlagged,
  deleteRun,
  saveProject,
  type DetectProject,
  type DetectRunRecord,
} from "./detectStore";
import {
  addFactorToUserLibrary,
  updateUserLibraryFactor,
  type UserLibraryFactor,
} from "./userFactorLibraries";

const NAME_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

export function emptyFactorBodyTemplate(
  name: string,
  description: string,
): string {
  const doc = (description || name).replace(/\\/g, "\\\\").replace(/"""/g, "'''");
  return `def ${name}(self):\n    """${doc}"""\n    return self.close.pct_change(5)\n`;
}

/** 用户库新建空因子（尚无公式 → formulaReady=false，列表黄色） */
export async function createEmptyUserFactor(opts: {
  libraryId: number;
  name: string;
  description: string;
  categoryLabel: string;
}): Promise<UserLibraryFactor> {
  const name = (opts.name || "").trim();
  const description = (opts.description || "").trim();
  const categoryLabel = (opts.categoryLabel || "").trim() || "其他";
  if (!name) throw new Error("请填写因子代码名");
  if (!NAME_RE.test(name)) {
    throw new Error("代码名须为字母开头的标识符（字母/数字/下划线）");
  }
  if (!description) throw new Error("请填写中文解释");
  if (!opts.libraryId) throw new Error("请选择所属因子库");
  return addFactorToUserLibrary(opts.libraryId, {
    name,
    body: "",
    description,
    categoryLabel,
    formulaReady: false,
  });
}

/** 因子库点「检测」：打开/复用检测项目并进配置页 */
export async function openDetectForLibraryFactor(
  factor: Pick<FactorMeta, "name"> & Partial<FactorMeta>,
): Promise<DetectProject> {
  const tab = openDetectPlaceholderTab();
  try {
    let p = await openOrCreateForFactor(factor.name, factor.name);
    // 从因子库开始新检测，单因子使用库中最新公式；历史入口仍使用运行快照。
    if (factor.userLibraryId != null && factor.body?.trim() && p.config.factorCodes.length === 1) {
      p = await saveProject({ ...p, config: { ...p.config, source: { code: factor.body, name: factor.name } } });
    }
    navigateDetectTab(tab, p.id, p);
    return p;
  } catch (err) {
    try {
      tab?.close();
    } catch {
      /* ignore */
    }
    throw err;
  }
}

/** 检测成功后把公式写回用户库空/待更新因子 */
export async function persistFormulaAfterDetect(opts: {
  libraryId: number;
  factorId: number;
  body: string;
  description?: string;
}): Promise<UserLibraryFactor> {
  const body = (opts.body || "").trim();
  if (!body) throw new Error("因子代码为空，无法写入库");
  return updateUserLibraryFactor(opts.libraryId, opts.factorId, {
    body,
    description: opts.description,
    formulaReady: true,
  });
}

/** 仅用户库空因子为「待写公式」；内置因子无 body 也算已就绪 */
export function isFormulaPending(
  f: Pick<
    FactorMeta,
    "formulaReady" | "body" | "userLibraryId" | "library" | "tags"
  >,
): boolean {
  const isUserLib =
    f.userLibraryId != null ||
    (f.library || "").startsWith("user_lib_") ||
    (f.tags || []).includes("user_library");
  if (!isUserLib) return false;
  if (f.formulaReady === false) return true;
  if (f.formulaReady === true) return false;
  return !(f.body || "").trim();
}

export async function listDetectReports(): Promise<DetectRunRecord[]> {
  return listAllDetectRuns();
}

export async function setDetectReportRemark(
  runId: string,
  remark: string,
): Promise<DetectRunRecord> {
  return updateDetectRunRemark(runId, remark);
}

export async function setDetectReportFlagged(
  runId: string,
  flagged: boolean,
): Promise<DetectRunRecord> {
  return updateDetectRunFlagged(runId, flagged);
}

export async function removeDetectReport(runId: string): Promise<void> {
  await deleteRun(runId);
}
