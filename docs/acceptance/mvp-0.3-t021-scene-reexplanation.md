# MVP 0.3 T021：当前场景重解释版本服务

`POST /api/learning-units/{id}/classroom/scenes/{scene_key}/reexplanations` 接受 `simpler`、`deeper`、`another_example`。先以 owner、幂等键和基场景版本预约操作，并复用既有 `reexplanation_requested` 学习证据规则；该证据只表示提出需求，不表示内容已生成或掌握度提高。请求与证据在调用 Provider 前提交。

生成器只重写当前场景的讲解；已审核代码和练习按原内容及来源引用复制到新场景，旧场景与其他场景保持只读。新讲解通过版本化资源 schema 与 ReviewAgent 后，在 owner 锁内检查课堂 revision、generation_id、scene_key 和基版本；通过才原子发布新场景、资源与课堂版本。审核拒绝、Provider 失败或迟到输出保留旧正式版本。临时 token 不持久重放，同键重试只返回已提交操作状态，正式资源从课堂操作及学习单元读取。

`GET /api/learning-units/{id}` 的已发布场景增加 `scene_key` 与 `is_current`，可区分当前和只读旧版。OpenAPI 已同步。没有新增数据库迁移，使用已有课堂操作、学习证据、场景和资源表。正式资源写入后不可变，因此来源引用与提示词版本在首次插入时保存。

验证在独立 PostgreSQL 数据库 `edumind_t021_20260929` 完成，使用 FakeAdapter，无真实 Provider 调用：

```text
cd backend && .venv/bin/alembic upgrade head                         # 通过
cd backend && .venv/bin/pytest -q tests/test_scene_reexplanation_api.py tests/test_classroom_mode_api.py tests/test_classroom_speech_api.py tests/test_mvp03_openapi_contract.py --tb=short  # 36 passed
cd backend && .venv/bin/pytest -q --tb=short                           # 612 passed, 5 skipped
cd backend && .venv/bin/ruff check app tests/test_scene_reexplanation_api.py  # 通过
cd backend && .venv/bin/mypy --strict app                               # 85 source files 通过
python3 -m json.tool docs/api/openapi.yaml >/dev/null                   # 通过
git diff --check                                                        # 通过
```

定向测试覆盖新旧版本与其他场景不变、重复请求无重复 Provider 调用、并发只有一方发布、审核拒绝与审核不可用撤回临时内容、Provider 失败保留原资源、跨 owner 隔离及学习证据不增加掌握分。后续 T022 将这些服务接入学习控制与版本选择界面；`accepted/running` 操作断线后仍按 ADR-0005 读取持久状态，不承诺临时 token 重放。
