# T082：前置计划检查、显式路由与人工出口

ADR-0021方案A已接入shared-plan-v1完整生成与重解释链路：计划保存后、任何正文生成前执行plan_check，按完整业务Schema及源绑定校验后保存不可变证据。现白名单为空，issue/不确定进入PLAN_REVIEW_REQUIRED；明确指向原请求的澄清建议进入GOAL_CLARIFICATION_REQUIRED，两者操作failed；拒绝进入PLAN_REJECTED/rejected。无半成品人工案件、正文或发布，单元最终人工审核流程不变。

## 请求及路由

版本plan-check-prompt-v1纳入活动政策摘要，旧待审政策和旧冻结运行包不能原样继续。只转发绑定原请求、当前段范围、学习证据、完整未验证计划和目标相关参考视图；背景全目标表不作为本段必达要求。user_request锚点仅指原始请求字段，其他计划与参考分别归类；原始快照留服务端。Schema模型结果不含binding/proof/route权限。

StructuredRequest.stage是服务端属性，LearningStageGateway将生成/重建/映射/资源生成与审核/重查/单元审核明确分流，未知stage拒绝、无重试/回退，不比较Prompt文本。P0生产默认显式把两角色映射到同一已选Gateway；注入的诊断组合可分别绑定不同Gateway，不静默从环境建立新厂商路由。

[wire-capture.json](wire-capture.json)是实际DeepSeekResponsesAdapter+ProviderGateway在MockTransport下的完整合成请求：DeepSeek flash/none/2048计划生成和Luna/high/8192计划检查；保存Host、SNI、实际模型参数、全Schema、请求正文，未保存授权头或Key。原旧诊断路由文件保留不改；新实际请求必须用stage路由，不能复用旧Prompt相等路由运行冻结包。本证据不构成真实渠道Schema兼容或模型语义通过。

## 人工维护

`backend/.venv/bin/python scripts/review_plan_checks.py list` 默认摘要；`show <check_id> --body` / `--export <新路径>` 显式查看检查、不可变原请求/计划/参考/政策与附记。授权沿EDUMIND_REVIEWER_CONFIG的可信OS uid白名单，导出0600、不覆盖。`note <id> --check-digest ... --kind ... --reason ... --idempotency-key ...`仅追加四种审计处置，身份来自可信配置；相同语义幂等返回，冲突拒绝。没有approve_plan、resume或publish。真实案件决定0。

既有完整单元CLI --body同步包含同owner/unit/operation的plan_checks及附记，不混入其他操作，历史源计划也保留。SSE错误及GET恢复只返回固定码、stage/check_id，无私密材料；新增契约见docs/api/openapi.yaml的x-plan-check-contract。

## 验证及保留的失败

最终[pg-check-05.json](pg-check-05.json)：新隔离PG0032，9文件65通过、0跳过，1条原Starlette依赖deprecation警告。覆盖前置阻断/原请求澄清/拒绝、正常发布、完整单元待审、重解释、schema/审计缺失/超时终止、SSE与恢复、只读跨操作隔离、人工附记/导出/权限，以及两适配器实际Mock出站。12源码mypy、Ruff、OpenAPI JSON解析、workflow/diff通过。

pg-check-01首轮15失败（通过记录遗漏必填原因码、澄清错误遗漏check_id及连锁失败）；pg-check-02为跨文件夹具错误地断言全库决定数0，44通过1失败；修成当前owner作用域后pg-check-03为45通过，再加入技术失败/SSE后04为49通过，最终加入双路完整wire和原代理回归后05为65通过。所有失败原件保留，未改判据、删失败样本或用跳过冒充通过。

本任务Provider0，H仅hash维护、四旧停止账本保持，T040 blocked。持久共享修正许可/映射512/全部审核输出配置及180秒预算强化待T083；受限重建待T084，白名单仍空。新源码不复用旧冻结授权或改旧记录分数。后续T085再冻结独立准入包，真实请求另批。
