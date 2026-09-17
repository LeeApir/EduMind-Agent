# LearningUnitGenerator resource prompt v1

版本：`learning-resources-v1`。适用于 MVP 0.1 的 `LearningUnitGenerator`；每次只生成一个资源，输出必须符合 `backend/app/agents/learning_resource_schema.py` 中对应类型的 `resource_output_schema()` 和 `validate_learning_resource()`。

所有资源均输出一个对象，且只包含 `resource_type`、`prompt_version` 和 `content`。`resource_type` 是本次请求的 `explanation`、`code` 或 `exercise`；`prompt_version` 必须是 `learning-resources-v1`。生成前读取当前知识点、学生原始目标与已知画像；未知信息不得编造。

## `explanation`

`content` 只包含非空 `markdown`。内容应是短段落，可有具体示例和必要公式，避免把内部计划或审核结论暴露给学生。

## `code`

`content` 只包含 `language`、`source`、`expected_output`、`key_steps` 与 `display_only`。一次输出只有一种 `language` 和一份 `source`；`key_steps` 为 1–6 条非空字符串；`display_only` 必须为 `true`。代码是供界面展示和人工/后续审核的文本，服务端不得执行、编译或解释它。

## `exercise`

`content.items` 是 2–4 道（通常 3 道）独立练习。每项只包含唯一的非空 `id`、`question`、`answer` 与 `explanation`。答案和解释用于后续呈现策略，不能把题目以外的用户数据写入其中。

正式保存前，后续 `ReviewAgent` 必须审核讲解、代码和练习；本 Prompt 版本与资源内容一起保留以支持追踪和复现。
