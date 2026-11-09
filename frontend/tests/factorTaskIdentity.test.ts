import assert from 'node:assert/strict';
import test from 'node:test';
import {
  createSingleFlight,
  ensureTopicForProject,
  runTaskCreation,
  type EnsureTopicDeps,
  type TaskIdentity,
} from '../src/lib/factorTaskIdentity.ts';

test('创建请求 HTTP 失败：保留项目身份，重试不重复建任务', async () => {
  let topics: Array<{ id: string; branch_id?: string }> = [];
  let createCalls = 0;
  const deps: EnsureTopicDeps = {
    listProjectTopics: async () => topics,
    createTopic: async () => {
      createCalls += 1;
      throw new Error('503 Service Unavailable');
    },
  };
  await assert.rejects(() => ensureTopicForProject({ projectId: 'p1' }, deps), /任务身份已保留/);
  assert.equal(createCalls, 1);
  // 第二次重试：服务端仍没有任务，才真正新建一次。
  deps.createTopic = async () => {
    createCalls += 1;
    topics = [{ id: 't1', branch_id: 'b1' }];
    return topics[0];
  };
  const task = await ensureTopicForProject({ projectId: 'p1' }, deps);
  assert.deepEqual(task, { projectId: 'p1', topicId: 't1', branchId: 'b1' });
  assert.equal(createCalls, 2);
});

test('创建成功但响应丢失：重试先查项目已有任务，不重复建', async () => {
  const serverTopics = [{ id: 't-lost', branch_id: 'b-lost' }];
  let createCalls = 0;
  const deps: EnsureTopicDeps = {
    listProjectTopics: async () => serverTopics,
    createTopic: async () => {
      createCalls += 1;
      throw new Error('network timeout after server commit');
    },
  };
  // 等价于第一次请求已提交、客户端没拿到响应；身份只保留 projectId。
  const task = await ensureTopicForProject({ projectId: 'p1' }, deps);
  assert.equal(task.topicId, 't-lost');
  assert.equal(task.branchId, 'b-lost');
  assert.equal(createCalls, 0, '发现服务端已有任务时不得再次创建');
});

test('项目下出现多条任务：拒绝任意取旧任务', async () => {
  await assert.rejects(
    () =>
      ensureTopicForProject(
        { projectId: 'p1' },
        {
          listProjectTopics: async () => [{ id: 'old' }, { id: 'new' }],
          createTopic: async () => ({ id: 'never' }),
        },
      ),
    /多条挖掘任务/,
  );
});

test('创建响应缺首分支：启动前重新读取台账补齐分支', async () => {
  let ledgerReads = 0;
  const result = await runTaskCreation(
    { projectId: 'p1', topicId: 't1' },
    true,
    {
      listProjectTopics: async () => [],
      createTopic: async () => ({ id: 'never' }),
      loadLedger: async (topicId) => {
        ledgerReads += 1;
        assert.equal(topicId, 't1');
        return { branches: [{ id: 'b-first' }] };
      },
      startF0: async (topicId, branchId) => {
        assert.equal(topicId, 't1');
        assert.equal(branchId, 'b-first');
      },
    },
  );
  assert.equal(ledgerReads, 1);
  assert.equal(result.started, true);
  assert.equal(result.identity.branchId, 'b-first');
});

test('首分支确实缺失：返回可见错误并保留任务身份，不假装启动', async () => {
  const result = await runTaskCreation(
    { projectId: 'p1', topicId: 't1' },
    true,
    {
      listProjectTopics: async () => [],
      createTopic: async () => ({ id: 'never' }),
      loadLedger: async () => ({ branches: [] }),
      startF0: async () => {
        throw new Error('must not start');
      },
    },
  );
  assert.equal(result.started, false);
  assert.match(result.error || '', /首分支尚未就绪/);
  assert.deepEqual(result.identity, { projectId: 'p1', topicId: 't1' });
});

test('保存草稿不启动，创建并启动才调用 F0', async () => {
  let f0Calls = 0;
  const base = {
    listProjectTopics: async () => [{ id: 't1', branch_id: 'b1' }],
    createTopic: async () => ({ id: 'never' }),
    loadLedger: async () => ({ branches: [{ id: 'b1' }] }),
    startF0: async () => {
      f0Calls += 1;
    },
  };
  const draft = await runTaskCreation({ projectId: 'p1' }, false, base);
  assert.equal(draft.started, false);
  assert.equal(f0Calls, 0, '草稿不得调用 F0');
  const launched = await runTaskCreation({ projectId: 'p1' }, true, base);
  assert.equal(launched.started, true);
  assert.equal(f0Calls, 1);
});

test('启动请求失败：保留任务身份并给出重试提示', async () => {
  const result = await runTaskCreation(
    { projectId: 'p1', topicId: 't1', branchId: 'b1' },
    true,
    {
      listProjectTopics: async () => [],
      createTopic: async () => ({ id: 'never' }),
      loadLedger: async () => ({ branches: [{ id: 'b1' }] }),
      startF0: async () => {
        throw new Error('502 Bad Gateway');
      },
    },
  );
  assert.equal(result.started, false);
  assert.match(result.error || '', /重试不会重复建任务/);
  assert.deepEqual(result.identity, { projectId: 'p1', topicId: 't1', branchId: 'b1' });
});

test('重复点击/并发重试：同一时刻只执行一次', async () => {
  let calls = 0;
  let release!: () => void;
  const blocked = new Promise<void>((resolve) => {
    release = resolve;
  });
  const once = createSingleFlight(async () => {
    calls += 1;
    await blocked;
    return 'created';
  });
  const first = once();
  const second = once();
  assert.deepEqual(await second, { skipped: true });
  release();
  assert.deepEqual(await first, { skipped: false, value: 'created' });
  assert.equal(calls, 1);
});

test('重试沿用同一 projectId/topicId 身份', async () => {
  const seen: TaskIdentity[] = [];
  const deps = {
    listProjectTopics: async () => [],
    createTopic: async () => ({ id: 't-new', branch_id: 'b-new' }),
    loadLedger: async () => ({ branches: [{ id: 'b-new' }] }),
    startF0: async () => {
      throw new Error('timeout');
    },
  };
  const first = await runTaskCreation({ projectId: 'p1' }, true, deps);
  seen.push(first.identity);
  const retry = await runTaskCreation(first.identity, true, {
    ...deps,
    startF0: async () => undefined,
  });
  seen.push(retry.identity);
  assert.deepEqual(seen[0], seen[1]);
  assert.equal(seen[0].projectId, 'p1');
  assert.equal(seen[0].topicId, 't-new');
});
