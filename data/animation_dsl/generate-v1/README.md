# animation-dsl-generate-v1

prompt.md 原字节复制自已批准 ADR-0010 的生成附件。T026 将指令接入 quality 档位，附本地 schema/policy、服务端参考和最小意图，不添加完整对话。运行时保存实际 Prompt、输入与采样摘要；最多两次定向修正，每次全量本地编译及独立 review。

本模块仅返回候选/模板计划，未创建 Job、执行 Scene 或发布媒体。目录模式与默认拒绝调用预算不变；实际测试开放仍按 ADR-0011 独立审批。
