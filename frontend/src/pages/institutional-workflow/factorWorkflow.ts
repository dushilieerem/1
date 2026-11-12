/** PRD F1–F6 contract. Navigation never grants validation or publication. */
export const factorStages = [
  { id: 'F1', title: '资产复用', action: '建立研究任务', agent: '因子研究 Agent' },
  { id: 'F2', title: '研究假设', action: '保存假设与验证计划', agent: '因子研究 Agent' },
  { id: 'F3', title: '工程计算', action: '校验并计算因子', agent: '因子实验 Agent' },
  { id: 'F4', title: '研发检验', action: '运行研发检验', agent: '因子实验 Agent' },
  { id: 'F5', title: '独立验证', action: '冻结并提交独立验证', agent: '独立验证 Agent' },
  { id: 'F6', title: '资产与准入', action: '整理因子卡与准入证据', agent: '因子资产 / 候选评审 Agent' },
] as const;
export type FactorStage = typeof factorStages[number]['id'];
export interface FactorEvidence {
  currentVersion: string;
  development?: { version: string; reportId: string; passed: boolean };
  frozenVersion?: string;
  independent?: { version: string; reportId: string; passed: boolean; isolated: boolean };
}
/** Display helper only: backend must enforce equivalent evidence checks. */
export function factorGate(stage: FactorStage, evidence: FactorEvidence): string | null {
  if (stage !== 'F5' && stage !== 'F6') return null;
  const d = evidence.development;
  if (!d?.reportId || !d.passed || d.version !== evidence.currentVersion) return '需要当前版本通过研发检验的真实报告';
  if (stage === 'F5') return null;
  const v = evidence.independent;
  if (evidence.frozenVersion !== evidence.currentVersion) return '需要冻结当前候选版本';
  if (!v?.reportId || !v.passed || !v.isolated || v.version !== evidence.currentVersion || v.reportId === d.reportId) return '需要当前冻结版本的独立验证证据';
  return null;
}
