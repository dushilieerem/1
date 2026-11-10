-- Target svquant_zxd_dev only; captured schema statements, never executed on source.
CREATE TABLE IF NOT EXISTS users (
              id              BIGSERIAL PRIMARY KEY,
              username        TEXT NOT NULL UNIQUE,
              email           TEXT UNIQUE,
              password_hash   TEXT NOT NULL,
              role            TEXT NOT NULL DEFAULT 'user',
              status          TEXT NOT NULL DEFAULT 'active',
              display_name    TEXT,
              ai_quota_daily  INTEGER NOT NULL DEFAULT 200,
              created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT users_role_chk CHECK (role IN ('user', 'admin')),
              CONSTRAINT users_status_chk CHECK (status IN ('active', 'disabled'))
            );
CREATE INDEX IF NOT EXISTS idx_users_status ON users (status);
CREATE TABLE IF NOT EXISTS auth_login_failures (
              username     TEXT PRIMARY KEY,
              failures     INTEGER NOT NULL DEFAULT 0,
              locked_until TIMESTAMPTZ,
              updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS cover_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS headline TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS inst_orgs (
              id          BIGSERIAL PRIMARY KEY,
              code        TEXT NOT NULL UNIQUE,
              name_cn     TEXT NOT NULL,
              name_en     TEXT,
              status      TEXT NOT NULL DEFAULT 'active',
              created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT inst_orgs_status_chk CHECK (status IN ('active', 'disabled'))
            );
CREATE TABLE IF NOT EXISTS inst_members (
              id          BIGSERIAL PRIMARY KEY,
              org_id      BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
              user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              role        TEXT NOT NULL,
              title_cn    TEXT,
              status      TEXT NOT NULL DEFAULT 'active',
              created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT inst_members_role_chk CHECK (
                role IN ('manager', 'partner', 'chairman', 'risk', 'execution', 'monitoring', 'quant_researcher', 'quant_reviewer')
              ),
              CONSTRAINT inst_members_status_chk CHECK (status IN ('active', 'disabled')),
              CONSTRAINT inst_members_org_user_key UNIQUE (org_id, user_id)
            );
CREATE INDEX IF NOT EXISTS idx_inst_members_user ON inst_members (user_id, status);
CREATE TABLE IF NOT EXISTS detect_projects (
                  id            TEXT NOT NULL,
                  user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  name          TEXT NOT NULL,
                  factor_name   TEXT NOT NULL,
                  description   TEXT NOT NULL DEFAULT '',
                  config        JSONB NOT NULL DEFAULT '{}'::jsonb,
                  run_count     INTEGER NOT NULL DEFAULT 0,
                  is_sample     BOOLEAN NOT NULL DEFAULT FALSE,
                  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  PRIMARY KEY (user_id, id)
                );
CREATE INDEX IF NOT EXISTS idx_detect_projects_user_updated ON detect_projects (user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS detect_runs (
                  id            TEXT NOT NULL,
                  user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  project_id    TEXT NOT NULL,
                  factor_name   TEXT NOT NULL,
                  description   TEXT NOT NULL DEFAULT '',
                  request       JSONB NOT NULL DEFAULT '{}'::jsonb,
                  result        JSONB NOT NULL DEFAULT '{}'::jsonb,
                  finished_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  elapsed_sec   DOUBLE PRECISION NOT NULL DEFAULT 0,
                  PRIMARY KEY (user_id, id),
                  CONSTRAINT detect_runs_project_fk
                    FOREIGN KEY (user_id, project_id)
                    REFERENCES detect_projects (user_id, id) ON DELETE CASCADE
                );
CREATE INDEX IF NOT EXISTS idx_detect_runs_project ON detect_runs (user_id, project_id, finished_at DESC);
ALTER TABLE detect_runs
                  ADD COLUMN IF NOT EXISTS remark TEXT NOT NULL DEFAULT '';
ALTER TABLE detect_runs
                  ADD COLUMN IF NOT EXISTS flagged BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_detect_runs_user_finished ON detect_runs (user_id, finished_at DESC);
CREATE TABLE IF NOT EXISTS strategy_projects (
              id            TEXT NOT NULL,
              user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              name          TEXT NOT NULL,
              description   TEXT NOT NULL DEFAULT '',
              config        JSONB NOT NULL DEFAULT '{}'::jsonb,
              run_count     INTEGER NOT NULL DEFAULT 0,
              is_sample     BOOLEAN NOT NULL DEFAULT FALSE,
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (user_id, id)
            );
ALTER TABLE strategy_projects ADD COLUMN IF NOT EXISTS is_sample BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_strategy_projects_user_updated ON strategy_projects (user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS strategy_runs (
              id            TEXT NOT NULL,
              user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              project_id    TEXT NOT NULL,
              name          TEXT NOT NULL DEFAULT '',
              description   TEXT NOT NULL DEFAULT '',
              request       JSONB NOT NULL DEFAULT '{}'::jsonb,
              result        JSONB NOT NULL DEFAULT '{}'::jsonb,
              finished_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              elapsed_sec   DOUBLE PRECISION NOT NULL DEFAULT 0,
              verified      BOOLEAN NOT NULL DEFAULT FALSE,
              result_hash   TEXT,
              PRIMARY KEY (user_id, id),
              CONSTRAINT strategy_runs_project_fk
                FOREIGN KEY (user_id, project_id)
                REFERENCES strategy_projects (user_id, id) ON DELETE CASCADE
            );
CREATE INDEX IF NOT EXISTS idx_strategy_runs_project ON strategy_runs (user_id, project_id, finished_at DESC);
ALTER TABLE strategy_runs ADD COLUMN IF NOT EXISTS remark TEXT NOT NULL DEFAULT '';
ALTER TABLE strategy_runs ADD COLUMN IF NOT EXISTS flagged BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE strategy_runs ADD COLUMN IF NOT EXISTS verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE strategy_runs ADD COLUMN IF NOT EXISTS result_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_strategy_runs_user_finished ON strategy_runs (user_id, finished_at DESC);
CREATE TABLE IF NOT EXISTS ai_usage (
              id           BIGSERIAL PRIMARY KEY,
              user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              run_id       TEXT NOT NULL,
              skill        TEXT NOT NULL,
              tokens_in    INTEGER NOT NULL DEFAULT 0,
              tokens_out   INTEGER NOT NULL DEFAULT 0,
              created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
CREATE INDEX IF NOT EXISTS idx_ai_usage_user_day ON ai_usage (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_usage_run ON ai_usage (run_id);
CREATE TABLE IF NOT EXISTS app_audit_logs (
              id            BIGSERIAL PRIMARY KEY,
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              user_id       BIGINT,
              username      TEXT,
              role          TEXT,
              action        TEXT NOT NULL,
              module        TEXT,
              resource      TEXT,
              method        TEXT,
              path          TEXT,
              status_code   INTEGER,
              duration_ms   INTEGER,
              ip            TEXT,
              user_agent    TEXT,
              detail        TEXT,
              request_id    TEXT
            );
CREATE INDEX IF NOT EXISTS idx_app_audit_logs_created ON app_audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_app_audit_logs_user ON app_audit_logs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_app_audit_logs_module ON app_audit_logs (module, created_at DESC);
CREATE TABLE IF NOT EXISTS user_custom_factors (
              id            BIGSERIAL PRIMARY KEY,
              user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              name          TEXT NOT NULL,
              method_name   TEXT NOT NULL UNIQUE,
              body          TEXT NOT NULL,
              description   TEXT NOT NULL DEFAULT '',
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (user_id, name)
            );
CREATE INDEX IF NOT EXISTS idx_user_custom_factors_user ON user_custom_factors (user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS user_factor_libraries (
                  id            BIGSERIAL PRIMARY KEY,
                  user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  name          TEXT NOT NULL,
                  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  UNIQUE (user_id, name)
                );
CREATE INDEX IF NOT EXISTS idx_user_factor_libraries_user ON user_factor_libraries (user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS user_library_factors (
                  id              BIGSERIAL PRIMARY KEY,
                  library_id      BIGINT NOT NULL
                    REFERENCES user_factor_libraries(id) ON DELETE CASCADE,
                  user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  name            TEXT NOT NULL,
                  method_name     TEXT NOT NULL,
                  body            TEXT NOT NULL,
                  description     TEXT NOT NULL DEFAULT '',
                  category_label  TEXT NOT NULL DEFAULT '其他',
                  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  UNIQUE (library_id, name),
                  UNIQUE (user_id, name)
                );
CREATE INDEX IF NOT EXISTS idx_user_library_factors_lib ON user_library_factors (library_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_library_factors_user ON user_library_factors (user_id, updated_at DESC);
ALTER TABLE user_library_factors
                  ADD COLUMN IF NOT EXISTS formula_ready BOOLEAN NOT NULL DEFAULT TRUE;
CREATE TABLE IF NOT EXISTS factor_dashboard_metrics (
                  factor_name TEXT NOT NULL,
                  library TEXT NOT NULL DEFAULT '',
                  universe TEXT NOT NULL,
                  period TEXT NOT NULL,
                  filter_limit_up SMALLINT NOT NULL CHECK (filter_limit_up IN (0, 1)),
                  filter_suspended SMALLINT NOT NULL CHECK (filter_suspended IN (0, 1)),
                  rules_version TEXT NOT NULL DEFAULT 'yg_v1',
                  name_cn TEXT,
                  ic_mean DOUBLE PRECISION,
                  ic_std DOUBLE PRECISION,
                  ir DOUBLE PRECISION,
                  rank_ic DOUBLE PRECISION,
                  q1_return DOUBLE PRECISION,
                  q5_return DOUBLE PRECISION,
                  long_short_spread DOUBLE PRECISION,
                  turnover DOUBLE PRECISION,
                  q1_turnover DOUBLE PRECISION,
                  q5_turnover DOUBLE PRECISION,
                  coverage_pool DOUBLE PRECISION,
                  coverage_total DOUBLE PRECISION,
                  win_rate DOUBLE PRECISION,
                  volatility DOUBLE PRECISION,
                  sharpe DOUBLE PRECISION,
                  annual_return DOUBLE PRECISION,
                  max_drawdown DOUBLE PRECISION,
                  error TEXT,
                  ic_unavailable_reason TEXT,
                  computed_at TIMESTAMPTZ NOT NULL,
                  PRIMARY KEY (
                    factor_name, library, universe, period,
                    filter_limit_up, filter_suspended, rules_version
                  )
                );
ALTER TABLE factor_dashboard_metrics
                ADD COLUMN IF NOT EXISTS ic_unavailable_reason TEXT;
ALTER TABLE factor_dashboard_metrics
                ADD COLUMN IF NOT EXISTS turnover DOUBLE PRECISION;
CREATE INDEX IF NOT EXISTS idx_factor_dashboard_metrics_query
                ON factor_dashboard_metrics
                  (universe, period, filter_limit_up, filter_suspended,
                   rules_version, library, factor_name);
CREATE TABLE IF NOT EXISTS factor_dashboard_legacy_imports (
                  migration_key TEXT PRIMARY KEY,
                  source_rows BIGINT NOT NULL DEFAULT 0,
                  imported_rows BIGINT NOT NULL DEFAULT 0,
                  skipped_rows BIGINT NOT NULL DEFAULT 0,
                  completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
CREATE TABLE IF NOT EXISTS re_factor_catalog_snapshot (
              scope TEXT PRIMARY KEY,
              content_hash TEXT NOT NULL,
              payload JSONB NOT NULL,
              fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              fetched_at_unix DOUBLE PRECISION NOT NULL,
              factor_count INT NOT NULL DEFAULT 0,
              library_count INT NOT NULL DEFAULT 0,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
CREATE TABLE IF NOT EXISTS re_factor_catalog_sync_log (
              id BIGSERIAL PRIMARY KEY,
              scope TEXT NOT NULL,
              changed BOOLEAN NOT NULL,
              content_hash TEXT,
              factor_count INT,
              message TEXT,
              detail JSONB,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
ALTER TABLE re_factor_catalog_sync_log
            ADD COLUMN IF NOT EXISTS detail JSONB;
CREATE TABLE IF NOT EXISTS invest_stocks (
      code TEXT PRIMARY KEY, name TEXT, pinyin TEXT, industry TEXT, asset TEXT,
      market TEXT,
      price DOUBLE PRECISION, prev_close DOUBLE PRECISION, open DOUBLE PRECISION,
      high DOUBLE PRECISION, low DOUBLE PRECISION, market_cap DOUBLE PRECISION,
      pe_ttm DOUBLE PRECISION, pb DOUBLE PRECISION, dividend_yield DOUBLE PRECISION,
      turnover DOUBLE PRECISION, volume DOUBLE PRECISION, amount DOUBLE PRECISION,
      beta DOUBLE PRECISION, next_report_date TEXT, updated_at TEXT
    );
CREATE TABLE IF NOT EXISTS invest_etf (
      code TEXT PRIMARY KEY, name TEXT, pinyin TEXT, industry TEXT, asset TEXT,
      market TEXT,
      price DOUBLE PRECISION, prev_close DOUBLE PRECISION, open DOUBLE PRECISION,
      high DOUBLE PRECISION, low DOUBLE PRECISION, market_cap DOUBLE PRECISION,
      pe_ttm DOUBLE PRECISION, pb DOUBLE PRECISION, dividend_yield DOUBLE PRECISION,
      turnover DOUBLE PRECISION, volume DOUBLE PRECISION, amount DOUBLE PRECISION,
      beta DOUBLE PRECISION, next_report_date TEXT, updated_at TEXT
    );
