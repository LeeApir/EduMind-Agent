# MVP-0.3-T017 专注与互动模式切换验收与交接

落实 ADR-0005 决定 B 的读写语义：课堂读/建/切模式均受 Cookie/CSRF/owner/版本/幂等契约约束，切回 focus 提交新 revision 与 `generation_id`，迟到旧输出无法写入当前会话。

## 实现

- [classroom.py](../../backend/app/services/classroom.py)（服务层）：
  - `owned_classroom` / `current_intro_scene`：owner 范围的当前课堂与「已就绪学习单元的最新已审核 intro 场景」只读查询，跨 owner 一律 404。
  - `create_classroom`：默认 focus / 仅导师 / revision=1，`scene_key` 固定 `intro`、`scene_version` 取最新已审核 intro。同 owner+unit 唯一约束是幂等底座，重复创建回放原快照；幂等键以 `(owner, idempotency_key)` 唯一持久化，同键异摘要 409、同键异单元（摘要含 unit_id）409。
  - `set_classroom_mode`：**幂等命中先于版本检查**；未命中时先 `lock_learning_owner`（owner 行锁串行化并发课堂写）再重查幂等、再 `If-Match` revision CAS。切模式提交 `revision += 1`、新的 `generation_id`，并把本次命令作为 `classroom_operations(kind='mode', status='published')` 记录，供迟到输出门禁与审计。`focus` 强制 `enabled_roles == []`。
- [classroom.py](../../backend/app/api/classroom.py)（API）：`GET` 快照、`POST` 建立（201/200）、`PATCH .../mode`（200），携带 `Idempotency-Key` 与 `If-Match-Classroom-Revision` 头；`CLASSROOM_VERSION_CONFLICT` 响应消息回传当前 revision。
- [0013_classroom_operations.py](../../backend/alembic/versions/0013_classroom_operations.py)：owner 范围幂等记录表，`kind ∈ {mode, control, speech, reexplanation, debate}`、`status ∈ {accepted, running, published, failed, cancelled, superseded}`，复合外键 `(user_id, learning_unit_id) → learning_units` 拒绝跨 owner；公开读模型 `GET /api/classroom-operations` 只暴露流式 kind（T019+）。
- 模式切换不调用任何 Provider/网关，纯数据库事务，满足「切换不自动触发持续模型调用」。

## 验证

- 迁移往返：`upgrade head` 空库依次通过 0001–0013；`downgrade 0012_classroom_sessions` 后 `classroom_operations` 表消失；`upgrade head` 恢复。
- [test_classroom_mode_api.py](../../backend/tests/test_classroom_mode_api.py) 11 项通过（隔离 PostgreSQL）：
  - 建前 GET 404；建默认 focus、幂等重放（同键与异键均 200 且快照一致）；CSRF/Origin 拒绝；无已发布 intro 场景建课堂 404。
  - focus→interactive→focus 切换、`enabled_roles` 规范化排序、revision 递增、`generation_id` 每次切换更新并持久读回。
  - 版本冲突 409 且消息含当前 revision；幂等重放先于版本检查（过期 If-Match 仍 200 回放）；同键异摘要 409；focus 带角色 422。
  - 跨 owner 读/建/切模式全部 404。
  - 并发同键同体幂等：恰好一次创建、两次均见 revision=2；并发异键同版本 CAS：恰好一方成功、另一方 `CLASSROOM_VERSION_CONFLICT`。
- OpenAPI 契约 [test_mvp03_openapi_contract.py](../../backend/tests/test_mvp03_openapi_contract.py) 7 项、T016 [test_classroom_persistence.py](../../backend/tests/test_classroom_persistence.py) 4 项通过。
- `ruff check app tests` 与 `mypy app`（77 源文件，strict）通过。

> 环境说明：全量后端在本 Windows 宿主运行 48 项失败，均与本任务无关、非回归——动画/链表模板及其依赖 API/Worker/媒体/事件测试因 `core.autocrlf=true` 且无 `.gitattributes` 使模板源文件 CRLF 导致 `template source approval digest mismatch`（摘要按 macOS LF 固化，前序 T006–T015 于 macOS 验证）；`test_first_screen_*` 为 Windows 毫秒计时断言抖动（`16.0 < 16.0`）；`test_animation_renderer` 依赖 Docker 镜像。T017 涉及课堂模型/服务/API/迁移/测试独立通过。

## 下一任务

T018「单 Tutor 按需角色编排」在 `enabled_roles` 与 `generation_id` 门禁底座上，编排默认专注下仅导师发言、按需基础/进阶角色发言，不自动触发持续模型调用。
