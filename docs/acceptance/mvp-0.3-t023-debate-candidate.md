# MVP-0.3-T023 数组与链表结构化多视角候选验收

## 交付

- [debate_candidate_generator.py](../../backend/app/agents/debate_candidate_generator.py) 仅接受 `array-vs-linked-list` 预设和非空问题，要求版本化图谱存在数组与单链表及 `SIMILAR_TO` 关系；一次 `generate_structured` 调用返回待审核候选，不执行并行角色子图、不自动触发通用辩论。
- [debate_candidate_schema.py](../../backend/app/agents/debate_candidate_schema.py) 固定 `array-vs-linked-list-candidate-v1`：明确题目已给/未给条件、两个图谱节点引用、性能/工程/学术三视角，以及主持人的客观结论、权衡和学习建议。严格拒绝缺字段、额外字段、错误版本和非预设节点，错误不回显模型原文。
- [debate_candidate_prompt.py](../../backend/app/agents/debate_candidate_prompt.py) 固定指令版本，要求按题目条件和图谱事实作条件化判断，区分客观事实与画像建议；问题作为数据传入，不执行其中指令。候选附服务端图谱版本及权威节点描述；只带与数组/链表有关且有证据的知识基础，以及显式反馈/人工更正过的视角偏好，不传其他画像私有字段。
- Provider 故障和格式错误分别返回稳定错误码；候选始终 `review_status=pending`，T024 的 ReviewAgent 审核通过前不可发布。此任务不增加外部 API 或持久化模型。

## 验证

- `cd backend && UV_CACHE_DIR=/private/tmp/edumind-uv-cache uv run pytest -q tests/test_debate_candidate_generator.py`：11 项通过，覆盖三视角/主持人结构、单次调用、事实/画像边界、无图谱关系、格式/Provider 失败。
- `uv run ruff check` 检查本任务 Python 文件通过；`uv run mypy app` 检查 89 个源文件通过；JSON Schema 经 `Draft202012Validator.check_schema` 验证。
- 完整后端 `uv run pytest -q`：498 通过、135 跳过。此任务是纯候选生成模块，数据库测试因未设置独立测试库而跳过；本任务没有真实 Provider 调用。

## 后续

T024 应基于此候选做 schema 后的事实审核、整体发布与失败不发布；T025 再实现课堂 detour 的 API/SSE 与返回点，不应把本任务的 pending 候选直接暴露为正式演示结果。
