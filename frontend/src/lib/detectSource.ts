import type { YgBacktestRequest } from "./ygApi";

/** 原文是运行与历史还原的共同来源；空字符串也是一次明确的编辑。 */
export type DetectSource = {
  code: string;
  name: string;
  library?: string | string[];
};

export function sourceFromRequest(req: YgBacktestRequest): DetectSource | undefined {
  if (typeof req.factor_code !== "string") return undefined;
  return { code: req.factor_code, name: req.factor_name || "factor", library: req.library_name };
}

export function sourceRequestParts(source: DetectSource) {
  if (!source.code.trim()) throw new Error("因子代码不能为空，请编写代码后再检测");
  const names = [...source.code.matchAll(/^def\s+([A-Za-z_]\w*)\s*\(/gm)].map((m) => m[1]);
  if (!names.includes(source.name)) {
    throw new Error(`请保留入口函数 def ${source.name}(self)，修改因子名称请到因子库编辑`);
  }
  return {
    factor_name: source.name,
    factor_code: source.code,
    ...(source.library ? { library_name: source.library } : {}),
  };
}
