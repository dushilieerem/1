/**
 * 挖掘任务创建/启动的可恢复身份处理。
 *
 * 创建链路分两步：本地/服务端项目 → 量化挖掘任务（topic）。
 * 任何一步的响应丢失都不能让前端丢掉已创建对象，否则重试会重复建任务。
 * 这里只做可注入依赖的纯逻辑，便于用隔离替身注入 HTTP 失败/超时。
 */

export type TaskIdentity = {
  projectId: string;
  topicId?: string;
  branchId?: string;
};

export type TopicListItem = {
  id: string;
  branch_id?: string | null;
};

export type EnsureTopicDeps = {
  listProjectTopics: (projectId: string) => Promise<TopicListItem[]>;
  createTopic: (projectId: string) => Promise<TopicListItem>;
};

/**
 * 确保项目只有一条可继续使用的挖掘任务。
 *
 * 已有 topicId 直接返回；否则先查项目下已有任务（覆盖“创建成功但响应丢失”），
 * 再决定是否真的新建。这样重试不会重复建任务。
 */
export async function ensureTopicForProject(
  identity: TaskIdentity,
  deps: EnsureTopicDeps,
): Promise<TaskIdentity> {
  if (identity.topicId) return identity;
  let existing: TopicListItem[] = [];
  try {
    existing = await deps.listProjectTopics(identity.projectId);
  } catch {
    // 查询失败时不能贸然新建；把错误抛给上层，保留 projectId 供下次重试。
    throw new Error('已创建项目，但读取其挖掘任务失败；任务身份已保留，请直接重试。');
  }
  if (existing.length > 1) {
    // 后端契约为 (user, org, project) 唯一；出现多条时必须人工核对，
    // 不能任意取旧任务导致用户继续到错误研究。
    throw new Error('项目下存在多条挖掘任务，已停止自动选择；任务身份已保留，请人工核对。');
  }
  const found = existing[0];
  if (found) {
    return {
      ...identity,
      topicId: found.id,
      branchId: identity.branchId || found.branch_id || undefined,
    };
  }
  try {
    const created = await deps.createTopic(identity.projectId);
    return {
      ...identity,
      topicId: created.id,
      branchId: identity.branchId || created.branch_id || undefined,
    };
  } catch (e) {
    throw new Error(
      '已创建项目，但建挖掘任务失败：' +
        (e instanceof Error ? e.message : String(e)) +
        '；任务身份已保留，请直接重试（会先检查是否已创建，不会重复建任务）。',
    );
  }
}

export type EnsureBranchDeps = {
  loadLedger: (topicId: string) => Promise<{ branches?: Array<{ id: string }> }>;
};

/**
 * 启动前确保有首分支。创建响应里缺 branchId 时重新读台账，
 * 而不是把“未就绪”永久当成不可启动。
 */
export async function ensureBranchForStart(
  identity: TaskIdentity,
  deps: EnsureBranchDeps,
): Promise<{ identity: TaskIdentity; error?: string }> {
  if (!identity.topicId) {
    return { identity, error: '挖掘任务尚未创建，不能启动。' };
  }
  if (identity.branchId) return { identity };
  try {
    const ledger = await deps.loadLedger(identity.topicId);
    const first = ledger.branches?.[0]?.id;
    if (first) return { identity: { ...identity, branchId: first } };
  } catch {
    // 下面给出可重试的明确提示，不假装已启动。
  }
  return {
    identity,
    error: '挖掘任务已创建，但首分支尚未就绪；任务身份已保留，请稍后重试启动，不会重复建任务。',
  };
}

export type RunCreationDeps = EnsureTopicDeps &
  EnsureBranchDeps & {
    startF0: (topicId: string, branchId: string) => Promise<void>;
  };

export type RunCreationResult = {
  identity: TaskIdentity;
  started: boolean;
  error?: string;
};

/**
 * 创建/保存草稿/创建并启动共用流程。
 * - 草稿不调用 startF0；
 * - 启动前补齐首分支；
 * - 任何失败都返回已保留的任务身份，供页面显示错误和重试入口。
 */
export async function runTaskCreation(
  identity: TaskIdentity,
  start: boolean,
  deps: RunCreationDeps,
): Promise<RunCreationResult> {
  let task: TaskIdentity;
  try {
    task = await ensureTopicForProject(identity, deps);
  } catch (e) {
    return { identity, started: false, error: e instanceof Error ? e.message : String(e) };
  }
  if (!start) return { identity: task, started: false };
  const branch = await ensureBranchForStart(task, deps);
  if (branch.error) return { identity: branch.identity, started: false, error: branch.error };
  try {
    await deps.startF0(branch.identity.topicId!, branch.identity.branchId!);
    return { identity: branch.identity, started: true };
  } catch (e) {
    return {
      identity: branch.identity,
      started: false,
      error: '挖掘任务已创建，但启动请求失败：' + (e instanceof Error ? e.message : String(e)) + '；重试不会重复建任务。',
    };
  }
}

/** 并发/重复点击闸门：同一时刻只允许一个创建请求。 */
export function createSingleFlight<T>(fn: () => Promise<T>): () => Promise<{ skipped: true } | { skipped: false; value: T }> {
  let busy = false;
  return async () => {
    if (busy) return { skipped: true };
    busy = true;
    try {
      return { skipped: false, value: await fn() };
    } finally {
      busy = false;
    }
  };
}
