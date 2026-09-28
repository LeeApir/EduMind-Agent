# MVP-0.3-T016 课堂会话与角色上下文持久化验收与交接

[Alembic 0012](../../backend/alembic/versions/0012_classroom_sessions.py) 新增三张表，落实 ADR-0005 决定 A 的持久边界：

- `classroom_sessions`：每个 `(owner, learning_unit)` 至多一个当前课堂。保存 `scene_key` 与当前已发布 `scene_version`、`scene_progress`、`mode`（focus/interactive）、乐观 `revision`、全局单调 `message_cursor`、`enabled_roles`、当前 `generation_id`、`paused` 和可选 `detour` 返回点。复合外键 `(user_id, learning_unit_id) → learning_units(user_id, id)` 拒绝跨 owner 指向他人学习单元；`(user_id, learning_unit_id)` 唯一约束即「默认课堂只建一次」的幂等底座。
- `classroom_messages`：只追加的已提交消息。保存服务端 `message_cursor`（每会话单调）、`role`（tutor/beginner/advanced/student/system 及 performance/engineering/academic/moderator 演示角色）、创建时的 `session_revision` 与 `scene_version`、公开 `text` 或审核后 `resource_id` 引用、`visible` 可见状态。临时流式 token 不落库。
- `classroom_role_contexts`：按 `(owner, learning_unit, role, scene_key, scene_version)` 保存去敏 `summary` 与有限条 `message_refs`。`context_kind` 显式区分课堂角色（tutor/beginner/advanced）与多视角职责（performance/engineering/academic/moderator），并用 CHECK 约束禁止两类互串，满足「课堂角色与多视角职责上下文分开」。

本任务只交付持久原语，不包含服务层 CAS/幂等逻辑与 API（T017–T020）。

## 验证

- 迁移往返：空库 `alembic upgrade head` 依次通过 0001–0012；`alembic downgrade 0011_animation_cancel_key` 后 `classroom_*` 三表均不存在；`alembic upgrade head` 恢复三表。
- [test_classroom_persistence.py](../../backend/tests/test_classroom_persistence.py) 4 项数据库测试通过：
  - 同一 owner+unit 第二个当前课堂被唯一约束拒绝、跨 owner 指向他人学习单元被复合外键拒绝、`mode` 越界被 CHECK 拒绝。
  - 消息游标每会话单调（重复游标拒绝）、跨 owner 写入他人会话消息被复合外键拒绝。
  - `context_kind` 与 `role` 的两类配对互斥被 CHECK 拒绝、同角色同场景同版本唯一、新场景版本可建新上下文。
  - 新引擎重启后读回相同的会话、模式/版本/游标/角色启用/暂停与已提交消息。
- `ruff check` 与 `mypy` 通过。

> 环境说明：本 Windows 宿主上 `app/main.py` 因动画缓存 `app/services/animation_cache.py` 使用 POSIX `fcntl` 而无法导入（前序 T006–T015 于 macOS 验证，commit `980caf7`），导致依赖 `app.main` 的全量后端测试无法在此宿主机收集。这是既有的跨平台缺口，非本任务回归；T016 涉及的模型/迁移/测试独立通过，其余全量回归需在具备 `fcntl` 的环境执行，或先做动画缓存跨平台修复。

## 下一任务

T017 需在上述 owner 约束、`revision` 乐观版本与 `message_cursor` 单调底座上实现专注/互动模式切换的 API/服务，不能在进程内存代替 PostgreSQL 状态。
