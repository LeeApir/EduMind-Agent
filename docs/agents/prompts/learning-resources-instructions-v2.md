# Learning resource instructions v2

指令版本：`learning-resources-instructions-v2`。输出 envelope/schema 仍为 `learning-resources-v1`，字段与严格校验不变；历史资源与测验继续兼容，不将旧数据重新标记为新指令生成。新生成及定向修正资源在 `generation_metadata.instruction_version` 保存实际指令版本，历史/原创候选可为 null。

实现：`backend/app/agents/learning_resource_prompt.py`。在原有类型教学指令之外增加 JSON 序列化契约：仅输出完整对象，Markdown/代码必须放入字符串；换行、引号与反斜杠必须按 JSON 转义，LaTeX 反斜杠亦需转义；禁止外层代码围栏、注释与尾逗号。讲解追加由 `json.dumps` 产生并经 schema 回归验证的完整示例，明确仅示范序列化，不要求复制其教学事实。

依据：2026-09-26 固定5次真实诊断中，3份讲解为 `STRUCTURED_JSON_INVALID`，而非 schema 字段不匹配或明确 token 上限。此改动针对已证实的 JSON 语法层失败类别；未保存生成正文，不能断定具体为裸换行、无效 LaTeX 转义或围栏。不得自动修复并算首次通过，不扩大 token 上限、不降低 schema，不更换 Provider。

参考 [OpenAI 官方结构化输出指导](https://developers.openai.com/api/docs/guides/structured-outputs) 的显式 schema 与评测原则；该文档的厂商保证不能套用于当前 DeepSeek Provider。真实效果尚待新的完整评测，离线示例解析与 mock 测试不算质量达标。
