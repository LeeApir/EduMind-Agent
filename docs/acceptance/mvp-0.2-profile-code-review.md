# MVP 0.2 渐进画像协作代码审查记录

## 审查基线与范围

- 审查日期：2026-09-25；基线为 `cf93ceb`，交付端为 `f2c79de`。
- 覆盖 `MVP-0.2-T006` 至 `T009` 的完成提交：`0aa65a1`、`3dcbb64`、`80b2d16`、`f2c79de`；另核对容器图谱路径修复 `74d0a3b`。
- 对照 `task.json` 的验收条件、`docs/PRD.md` §3.2、`docs/ADR/0003-learning-evidence-mastery-and-path-versioning.md` 和 `docs/api/openapi.yaml`。
- 本记录区分交付者自报验证、审查静态证据和后续独立回归。除非写明命令与结果，不把测试记录视为本次审查已独立复测。

## 审查过程

1. 2026-09-24：将远端 `origin/codex/mvp-0.2-t006` 快进到本地，确认 `HEAD=f2c79de` 且工作区干净；尚未合入 `main`。
2. 2026-09-25：核对四个任务的提交、任务账本和交接日志。发现 T008 已有 `80b2d16` 的 `Task-Completed` 标记及 `completed_at`，但账本仍写 `in_progress`；以治理提交更正为 `done`，历史日志原样保留。
3. 静态检查事件 schema、画像合并与持久化、迁移、API 鉴权/幂等、前端卡片和现有测试。下表记录待修复的问题与可复现路径。

## 发现与回归路径

| ID | 严重度 | 证据和可复现步骤 | 预期 | 后续任务 | 状态 |
| --- | --- | --- | --- | --- | --- |
| R1 | 高 | `create_transient_profile()` 每次学习都仅从新输入提取下一版本，没有合并已有手动修正。用同一 owner 建立画像、PATCH 修正字段、再次 POST `/api/learning-sessions`、GET `/api/profile/me` 比较修正值与证据。 | 修正值及其证据仍在最新版本，历史版本不变。 | T026 | 已修复并复测 |
| R2 | 高 | `record_profile_event()` 先查 owner+幂等键，再无竞争处理地提交。两个数据库会话同时以同一键、同一载荷 POST `/api/profile/events`，可能由唯一约束抛出未处理 `IntegrityError`。 | 只创建一条事件，两个请求返回同一 ID；不同载荷返回 409。 | T027 | 已修复并复测 |
| R3 | 中 | `ProfileCard` 仅挂载时读取；页面初次加载为 404 后完成学习，组件没有来自 `App` 的刷新信号。 | 首次学习创建画像后自动展示最新版本，不影响首段流式内容或编辑草稿。 | T028 | 待回归 |
| R4 | 中 | 事件与合并规则仅有代码常量；`profile_events` 和 `student_profiles` 不保存事件 schema 版本、合并规则版本或前一画像版本引用。 | 已保存记录能解释使用的 schema/规则版本和快照顺序，旧记录迁移后仍可读。 | T029 | 待回归 |

## 交付者提供的验证记录

- T006：后端 147 passed、15 skipped；Ruff/Mypy 通过。
- T007：临时 PostgreSQL 迁移往返；后端 167 passed；Ruff/Mypy 通过。
- T008：临时 PostgreSQL 迁移往返；后端 174 passed；Ruff/Mypy 通过。
- T009：前端 30 tests、类型检查、构建通过；Lint 0 error、97 warnings。
- 上述数字来自 `task.json` 和 `process.txt` 的交接记录；本轮独立验证结果按各修复任务完成情况追加。

## 独立修复与验证

### T026：跨学习会话保留手动修正

- 回归先因缺少 `merge_profile_snapshots` 在测试收集阶段失败；实现后 21 项定向测试通过。
- 新学习请求按来源优先级合并旧画像与新提取结果：手动修正优先于初始查询，同优先级的新证据才覆盖旧值；旧证据和历史版本保持不变。Provider 输出若伪造手动修正来源则降级为空提取，原有修正仍保留。
- 固定镜像 `postgres@sha256:cf78e766…` 的临时内存 PostgreSQL 从空库升级到 Alembic head；该库全量后端 `179 passed`（7 条依赖弃用警告）。`ruff check .` 与 `mypy app` 通过。

### T027：并发事件幂等

- 新回归使两个 PostgreSQL 会话都在插入前读到“无记录”，修复前同载荷与不同载荷两种竞争均失败；修复后均通过。
- 唯一约束冲突后回滚当前事务，再按 owner 与幂等键读回已提交事件：摘要相同返回原 ID，摘要不同转成稳定 `IDEMPOTENCY_CONFLICT`；其他完整性错误继续抛出。
- 定向 `7 passed`，隔离库全量后端 `181 passed`（7 条依赖弃用警告）；Ruff、Mypy 通过。

## 结题汇报取材边界

可以展示任务拆分、远端交付、快进集成、审查发现、回归修复和再验证的时间线。技术贡献以提交和文件为准，问题描述使用可复现事实；未完成的检查与未达成的验收照实标注。`main` 的阶段合并应在 MVP 0.2 闭环与退出验收完成后另行记录。
