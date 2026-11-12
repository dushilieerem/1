# FEAT-036 主站管理后台

| 项 | 内容 |
|---|---|
| 状态 | 首版可运行（用户管理 + 审计） |
| 日期 | 2026-10-31 |
| 入口 | `/admin`（仅 `role=admin`） |
| 代码 | `backend/app/routers/admin_users.py`、`backend/services/admin/user_admin_store.py`、`frontend/src/pages/AdminPage.tsx` |

## 1. 目标与范围

给主站管理员一个统一后台：

- **用户管理**：列表/搜索、按状态/角色筛选、禁用/启用、设为管理员/降为用户、重置密码。
- **系统审计**：复用既有 `app_audit_logs` 查询面板（模块/用户/动作/状态码/时间过滤、CSV 导出）。
- **安全约束**：不能禁用/降级当前管理员；不能禁用/降级最后一个有效管理员；所有写操作写审计。

## 2. 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/users?q=&status=&role=&limit=&offset=` | 用户列表 |
| POST | `/api/admin/users/{id}/status` | `{status: active/disabled}` |
| POST | `/api/admin/users/{id}/role` | `{role: user/admin}` |
| POST | `/api/admin/users/{id}/reset-password` | `{password}`，至少 6 位 |
| GET | `/api/admin/logs` | 既有审计查询 |
| POST | `/api/admin/logs/purge` | 既有审计清理 |

权限：全部要求 `require_admin`（服务端），前端菜单/路由只是展示。

## 3. 验证

| 项 | 结果 |
|---|---|
| 管理员登录 | 200 |
| `/api/admin/users` | 200；返回用户列表与总数 |
| `/api/admin/logs` | 200；返回审计列表与总数 |
| 前端 TypeScript/build | 通过 |
| 浏览器走查 | **未做** |

## 4. 已知缺口

- 没有分页 UI（接口支持 limit/offset；页面默认 100 条）。
- 没有批量操作、导出用户 CSV、登录设备管理。
- 找回密码仍走管理员重置；邮件自助找回待 SMTP/邮件服务。
- SSO、多租户管理后台、WORM 审计存储未做。
