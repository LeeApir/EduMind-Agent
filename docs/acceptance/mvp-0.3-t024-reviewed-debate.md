# MVP-0.3-T024 多视角结果审核与发布验收

## 交付

- 独立 Review 对完整候选的事实、问题条件、三视角与主持人总结给出版本化裁决。严重错误直接拒绝；可修正问题最多进行两次定向修正，每次重新审核，超时或格式错误不视为通过。
- `POST /api/learning-units/{unit_id}/classroom/debate` 使用课堂 revision、generation_id、owner 和幂等键保留操作；通过审核后一次事务写入正式结果并进入演示场景。失败、审核拒绝、版本冲突及断流不发布结果，原课堂状态保持不变。相同幂等键重放只返回持久操作状态，不再次调用 Provider。
- `GET .../debate/{result_id}` 只读取 owner 的已发布完整结果，包含问题条件、图谱依据、三视角、主持人结论及候选/审核版本与模型来源。`POST .../exit` 以幂等回执恢复课堂返回点；若原场景已有新版正式资源，返回当前已审核版本并标记 `version_changed`，消息游标不回拨。
- Alembic `0015_debate_results` 增加 owner 范围的正式结果表；OpenAPI 同步正式结果、detour 和错误码。待审核候选不进入该表，也不通过读取端点暴露。

## 验证

- 在隔离数据库 `edumind_t024_20260929` 执行 Alembic `upgrade head` 成功。数据库集成测试覆盖通过/严重错误拒绝/Review 超时、生成格式错误/超时、revision 冲突、owner 隔离、幂等重放、断流清理和退出回执；已发布 JSON 通过 OpenAPI Schema 校验。
- 独立 Review 单元测试覆盖正确与严重错误对照、修正后通过、两次修正上限、超时与畸形裁决。后端全量 `uv run pytest -q`：640 通过、5 跳过；新增契约断言后定向 API 7 项通过。
- `uv run ruff check app tests`、`uv run mypy app`（92 个源文件）、OpenAPI JSON 解析与 `git diff --check` 通过。Provider 使用 mock，未调用真实模型。

## 后续

T025 接入前端演示展示、刷新恢复与返回交互；T026 再实现显式视角反馈。旧操作缺少原始回执时保留既有 `409` 契约。
