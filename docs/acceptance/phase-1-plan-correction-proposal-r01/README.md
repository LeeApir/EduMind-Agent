# 计划纠错提案 r01（待批准，零调用）

本包仅交付契约、预算计算和候选任务，不实现自动计划重建、不批准任何真实请求。T079只读历史已独立提交 `154f282`；T040仍blocked，H01–H08输入与预标签已由Lee核对，继续封存且不用作开发材料。旧失败、未运行项、停止账本及旧冻结源码均保留。

建议先采用方案A：前置检查发现计划问题即停止当前操作，提供完整证据给维护者；只有满足独立验证条件的局部计划缺陷才可能一次重建。当前没有已批准验证器，因此自动重建默认不可达。不是把一次模型判断当成纠错能力证明。

## 1. 拟议最小契约

[contract.schema.json](contract.schema.json) 是完整业务候选Schema，不是生产Schema；[synthetic-record.json](synthetic-record.json) 是人工合成形状样例，不含真实课程或模型结果。[检查器](/Users/apir/Code/EduMind_Agent/scripts/check_plan_correction_proposal.py) 只检查离线一致性与预算，不执行任何路由、生成、迁移或语义证明。

| 对象 | 不可变内容及职责 |
| --- | --- |
| model_result | 五项检查覆盖、verdict、逐项finding及unresolved；不得写绑定摘要、proof或服务端route |
| anchor_catalog | 服务端从已绑定原请求/计划/相关参考快照建目录：source_kind、根快照digest、JSON Pointer、字段内UTF-8半开字节区间；完整原快照另存可核对 |
| binding | owner/unit/operation/plan ID及版本，计划/原输入/参考/政策摘要，服务端固定 |
| proof | 注册验证器ID/版本、前提摘要、绑定摘要、涉及finding/证据锚点与结论；不是模型提供的“已验证”声明 |
| server_assessment | 服务端决定accept_plan/rebuild_once/needs_human/clarify_user/reject/failed，记录原因及批准的proof IDs |
| rebuild_event | attempt恒为1，先记录reserved，后追加completed/failed；关联旧计划、触发检查、新计划及摘要，不覆盖旧事件 |
| resolution | 可信本机维护者追加clarification_needed/new_request_needed/false_positive_confirmed/rejected及理由；没有approve_plan或resume动作 |

拟新增 `learning_plan_checks`、`learning_plan_rebuild_events`、`learning_plan_check_resolutions` 三类不可变记录，经Alembic迁移。唯一键至少包括operation+plan+stage，重建预约另以operation+attempt唯一；服务端校验所有权及实际引用对象。请求/回答摘要只绑定有界安全记录，不存Key/原始推理。维护者身份沿现有可信本机OS白名单，不信任模型或请求体自报身份。

原请求是用户要求权威来源；计划只是模型承诺，背景参考不是本次必达目标。并列主题不以最长关键词裁决，缺信息不得补成事实。引用必须支持实际命题，邻近字段不能替代。字节相等和Schema通过只证明定位/结构，不证明语义。

离线检查器只验证摘要字段相等、引用存在及路由条件；实际源字节/JSON位置/摘要重算、验证器前提与正确性仍是PC-01/04实现和验收内容。当前白名单为空；不以A01算术特例、自然语言关键词或执行任意C程序充当通用验证器。

## 2. 分流与停止边界

| 情况 | 拟议处理 |
| --- | --- |
| 完整检查pass，无缺陷/未决，结构和绑定正确 | accept_plan，继续三类资源；不代表数学正确保证 |
| 局部计划内部冲突/无据承诺/计划覆盖缺口，全部由批准验证器确认 | 仅初次plan_check可rebuild_once，新版本必须重查 |
| 来源混淆、缺前提、未注册验证器、证据不能确认 | needs_human，不能把模型建议当重建许可 |
| 原请求确有歧义/互相冲突 | clarify_user，不能擅自改变用户要求 |
| 有据严重错误/unsafe_plan、已有reject | reject，不借“修复”自动降级 |
| Schema、网络、绑定、预算、超时失败 | failed，保存技术失败，不伪造质量判断 |

重建要求：模型verdict=issue、五项全检、无unchecked/unresolved、所有finding均获独立证明、目标均属于计划且限允许类别、未预约过重建。注册验证器必须在其适用域内以明确前提得出可检查结论；“无法保证”不能推出确定反例数值。模型单方面声称confirmed不成立。

资源局部问题继续沿现有最多2次修正，但共享额度可能更少；只修资源，不修改冻结计划。正文/单元阶段才发现计划问题时，本操作停止，不能再回到前置循环。新计划版本保留旧计划、旧候选和审核历史；若存在关联候选/案件，明确失效，不能复用旧审核或发布授权。新版本三份资源与各审核重新生成，最终仍需单元审核。

方案A的早期出口：operation终止为failed，使用不同语义码 `PLAN_REVIEW_REQUIRED` / `GOAL_CLARIFICATION_REQUIRED`，报告stage及check_id。不得把半成品塞进当前要求完整材料和最终四审核的人工案件；现有完整单元awaiting_human、approve/reject及发布规则不变。维护者可看问题及追加处置附记，附记不触发Provider或发布；需澄清时由用户明确发起新操作，使用新预算，不恢复旧180秒窗口，也不把模型计划复制为原用户要求。

方案B“人工批准早期计划后自动续跑”涉及新案件种类、权限、SSE/状态、等待超时和编辑闭环，明确不在本提案实现范围。方案A也涉及新的报告/错误码和持久化，须用户批准后同步ADR/API文档再开发。

## 3. 实际路由约束

生成/重建/目标映射/资源生成走generation角色；计划检查/重查/资源审核/单元审核走review角色。当前诊断组合为DeepSeek flash/none生成、Luna/high/8192审核，不设为业务硬依赖，也不改生产默认。

现诊断 `scripts/acceptance_support/luna_review_routing.py` 以首条Prompt是否等于资源审核INSTRUCTION选模型，新计划Prompt会误走生成路由。PC-02必须改为服务端可信stage与角色，离线捕获实际适配器的Host/SNI、model、reasoning、超时、输出上限、完整业务Schema与渠道投影。不得只改配置名即声称已路由。新计划Prompt与Schema投影须另行版本化与兼容验证；本提案不修改当前Prompt。

## 4. 共享预算（候选上限，不是调用授权）

[budget.json](budget.json) 列出全部22种计数。M为可选映射0/1，R为重建0/1，K为资源修正对数（一次生成+一次审核）。

- 基线请求数 `9 + M + 2R`：计划1、检查1、资源生成3、资源审核3、单元审核1；重建加生成及重查2。
- `K ≤ min(6, floor((20 - 9 - M - 2R)/2))`，无重建最多5对，有重建最多4对；每资源仍最多2对。
- 生成请求 `4+M+R+K`，审核请求 `5+R+K`，合计 `9+M+2R+2K ≤20`。

| M | R | K上限 | 总请求上限 | 最大输出Token |
| --- | --- | --- | --- | --- |
| 0 | 0 | 5 | 19 | 116736 |
| 1 | 0 | 5 | 20 | 117248 |
| 0 | 1 | 4 | 19 | 114688 |
| 1 | 1 | 4 | 20 | 115200 |

无修正/无重建为9或10次，输出55296或55808；重建后无资源修正为11或12次，输出65536或66048。拟定输出上限：映射512、计划/重建2048、资源/修正4096、所有审核8192。现映射max_output_tokens为空，512是待实现的新约束，不是现状描述。

输出公式：`512M + 2048(1+R) + 4096(3+K) + 8192(5+R+K)`。这是配置上限求和，不是实际Token或费用估计；输入取决于上游内容，本包未冻结输入总额，不宣称总Token有相同上限。费用不限不等于真实请求获准；本包授权真实请求为0。

20次必须覆盖可选映射，绝对180秒从映射前开始，单次最多60秒且不超过剩余时间，重试0、回退0。串行19/20请求不保证180秒完成，到时停止。共享槽位不保证三个资源都能各修2次。

实现时分开记“修正对许可”和“实际请求预约”，避免一次许可+2、每次发送再+1的重复计数。许可须原子保护后续必要调用尾部；每个实际请求仅预约一次，失败/中断不退款，不可重复使用许可。停止记录保留原因/未运行步骤，旧预算不重开。并发和崩溃恢复需真实隔离PG验证，算术脚本不能代替执行器证明。

## 5. 待确认任务与退出条件

[proposed-tasks.json](proposed-tasks.json) 拆PC-01–PC-05为契约持久化、检查与人工出口、持久预算、受验证器约束单次重建、独立准入准备。它们不是已领取活动任务，未新增后续PHASE任务号；确认后再按依赖建立活动任务，每项独立验证提交。

本次请确认：采用方案A人工出口；默认空验证器白名单及一次重建门槛；20次/180秒和共享5或4对资源修正；按PC-01–05串行拆分。确认设计也不自动批准真实Provider、H使用或解除T040。若无法定义可靠验证器，停留在检查+人工分流，不声称自动修复计划；以后真实验收仍须独立冻结并另批。

验证：`backend/.venv/bin/python scripts/check_plan_correction_proposal.py`、`backend/.venv/bin/python -m pytest -q scripts/tests/test_plan_correction_proposal.py`，以及Ruff/workflow/diff。合成一致性测试不构成模型质量、纠错成功或泛化证据。
