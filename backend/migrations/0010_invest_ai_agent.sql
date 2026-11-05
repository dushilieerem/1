-- H5 AI Agent 用户级提示词覆盖；按用户隔离，不修改全局 TaskSpec。
-- 编号 0010：与 0008/0009 的量化因子 Agent 任务迁移保持顺序。
CREATE TABLE IF NOT EXISTS invest_ai_agent_prompt (
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  task_id TEXT NOT NULL,
  prompt TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
  PRIMARY KEY (user_id, task_id)
);
