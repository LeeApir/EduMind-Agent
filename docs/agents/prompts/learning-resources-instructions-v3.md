# Learning resource instructions v3

指令版本 `learning-resources-instructions-v3`，schema/envelope仍 `learning-resources-v1`。保留v2序列化约束，额外将实际 `resource_output_schema()` JSON完整写入提示正文，明确嵌套required键、原字段名称/类型、代码expected_output/key_steps/display_only和每道题answer/explanation。API格式参数也保留同一schema，无字段放宽、解析修补或成功重试计数。

依据：2026-09-26两轮有界循环队列探针中，第二轮code:2出现 `STRUCTURED_SCHEMA_MISMATCH`，固定白名单关键字为 `required`。只证实缺少必填字段，未记录具体字段/模型正文，故不声称某一个字段一定缺失。完整schema由同一函数生成，避免手写字段契约与验证器失步。

参考 [官方结构化输出指导](https://developers.openai.com/api/docs/guides/structured-outputs) 的显式schema原则。当前DeepSeek是否严格遵守必须由真实基准验证，不采用OpenAI的厂商保证。此版本属于第二轮实质不同的修复：v2针对JSON序列化，v3针对必填结构可见性；若真实门禁仍不通过，按项目规范停止盲修并求助。
