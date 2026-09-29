# MVP 0.3 T035：课堂学习控制 API

T022 的前端验收依赖 `POST /api/learning-units/{id}/classroom/controls`，但该端点原先只有 ADR-0005/OpenAPI 设计契约。任务账本新增 T035 作为 T022 的前置；这项拆分只落实已批准的控制语义。

端点在 owner 锁内检查幂等键与课堂 revision，持久化原快照回执并更新 generation_id，防止旧发言在控制动作之后发布。暂停/继续不撤销证据；跳过只推进场景进度并按既有 `explicit_feedback:skip` 规则记录证据，掌握分不提高。资源选择要求当前场景已有审核发布的正式资源；动画还要求本 owner 当前场景已成功绑定媒体，不由控制动作创建 Job。资源选择写入去敏的 `resource_selected` 事件，事件 schema 从 v1 升至 v2，允许 explanation/animation 类型，但画像自动更新仍只处理既有 code/exercise 偏好。补前置要求目标为当前路径推荐的直接前置节点，保存路径版本及课堂返回点并暂停；继续时清除该返回点，失败不修改原课堂。演示 detour 由其专用退出操作处理，控制端点拒绝在演示期间覆盖它。

在独立 PostgreSQL 测试库 `edumind_t021_20260929` 验证，未调用真实 Provider：

```text
cd backend && .venv/bin/pytest -q tests/test_classroom_controls_api.py tests/test_profile_events.py tests/test_mvp03_openapi_contract.py --tb=short  # 26 passed
cd backend && .venv/bin/pytest -q --tb=short  # 617 passed, 5 skipped
cd backend && .venv/bin/ruff check app tests/test_classroom_controls_api.py tests/test_profile_events.py  # 通过
cd backend && .venv/bin/mypy --strict app  # 86 source files 通过
python3 -m json.tool task.json >/dev/null && python3 -m json.tool docs/api/openapi.yaml >/dev/null  # 通过
git diff --check  # 通过
```

定向测试覆盖暂停/继续及原回执、重复键摘要冲突、revision CAS 和并发只成功一方、跨 owner 隔离、跳过的场景进度与零掌握增益、资源未发布拒绝、补前置路径验证、返回点及恢复。后续 T022 接入界面时，前置 detour 的目标节点是导航状态；教学资源仍须通过正式学习单元读取或明确发起学习请求。
