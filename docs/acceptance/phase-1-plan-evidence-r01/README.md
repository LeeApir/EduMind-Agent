# T081：计划检查证据持久化

按用户批准的ADR-0021方案A，新增0032迁移与三张审计表：learning_plan_checks、learning_plan_rebuild_events、learning_plan_check_resolutions。没有接入生成流程、调用模型、实现自动重建或授予发布权限。

- 完整业务Schema承接冻结提案全部defs，本地额外核对源快照摘要、身份、五项覆盖/路由门槛、严格JSON Pointer与字符串内UTF-8半开区间。模型不能带入服务端授权字段。
- owner/unit/operation/plan复合FK隔离；检查stage唯一；事件预约唯一且completed/failed共享唯一终态；人工附记幂等键唯一。数据库触发器禁止三表UPDATE/DELETE，父对象RESTRICT防止级联丢证。存储服务只flush，由调用者负责事务。
- owned_plan_check不返回其他owner证据；人工附记只能记录四种处置，绑定预期检查摘要及可信调用方身份，无approve/发布/续跑动作。维护CLI权限入口将在T082接入。
- 默认验证器白名单为空，save_rebuild_event无法预约任何实际重建。终态执行编排尚待T084；本任务的合成原始DB事件仅验证约束，不代表实际能力。

## 实际验证

[pg-check-01.json](pg-check-01.json)：全新白名单隔离PostgreSQL迁移0032，12项新测试及旧只读/CLI/人工案件/发布共34通过，0跳过。覆盖重复stage/附记、跨owner读/写、不可变UPDATE/DELETE、坏快照/指针/范围/UTF-8、模型越权、无证明重建拒绝，以及旧案件构建兼容。所有课程、gateway及维护者均为合成夹具，不是实际课程签核。

[migrations.json](migrations.json)：有审计数据时downgrade明确失败并保留数据；另一个全新空库upgrade→downgrade→upgrade通过。

Ruff、两源码mypy、workflow、diff检查通过。初Ruff格式及object类型错误已修复，最初沙箱docker不可访问，获准后在同一测试容器隔离库运行；没有用跳过替代数据库证据。Provider0，真实课程决定0，H仅核对封存hash，旧四账本保持。T040仍blocked。

## 交接

生产Schema位于backend/app/services/plan_check.schema.json；存储服务plan_check.py；模型models/plan_check.py。当前缺少真实计划检查请求、显式stage路由及早期人工报告，由T082实现；共享预算T083、受限重建T084、准入冻结T085按依赖推进。默认空验证器必须保留；不能因协议已批准就把合成测试验证器加入生产。
