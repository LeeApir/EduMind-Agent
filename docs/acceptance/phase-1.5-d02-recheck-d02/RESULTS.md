# 最终D02 d02：首次规划校验失败，已停止并转方案重评

用户准确批准c4fd24e、ADR0040 A—C、合成外发、新窗口及费用例外（call_927331cbacc54aff861c1c319f46b1ea），manifest `53583b1fdd975d1c50772c2e6047436a86134af623d151436b669f9afda7496f`。新窗口2026-10-28 09:16:34（Asia/Shanghai）登记。本批只有一次 `--step`，实际1 HTTP200，首次本地规划校验不通过后立即stopped/threshold_unreachable；没有第二次生成、修复请求、传输重试或旧批次重启。未使用的4次请求不作为重试许可。

## 具体失败

DeepSeek官方deepseek-flash/none报告completed，返回的JSON能通过原 `free_course_planning.schema.json`。失败是其后的目标覆盖规则：规划生成4个objective，两个场景只引用其中3个。未被引用的是 `obj_two_scenes`，描述“课程按 2 个场景组织内容。”，来源“组织2个场景”。原校验器要求所有objective都被场景覆盖，最终统一抛出 `SCHEMA_INVALID`，入口再按首次失败停止。只读原始字节与原校验器复验确认，不改写响应、补引用或降低断言。

需要区分：规划实际确有两个场景，编排数量没有丢失；模型把这个编排约束也建成了学习目标，却未建立引用。当前契约允许这种分类混杂，又把所有目标按同一覆盖规则处理。这反映模型输出职责与程序契约的边界问题，不是本次已经发现新的链表事实或练习答案错误。

本次仅运行未改动的规划器 `free-course-plan-v1`；场景生成v5、两次sol审核及ADR0040新元数据策略都未进入真实执行。因此不能称自环修复已通过或再次失败，也不能称新审核兼容已完成真实验证。课程/场景生成数量均为0，两个审核未运行，标准slot_output/助手复核导入均0；没有可供逐题复核的新课程。

## 用量、状态和保存

1请求complete/0unknown，报告并可信结算1966输入/665总输出（合计2631）；实际收费/币种未知。此前相关29请求保留，新累计30请求、报告138390输入/31075总输出，非全项目累计。旧d01/r05及其unknown、失败与费用观察不改。

只读PG导出含1 attempt、1 settlement，0已准入plan、0 scene。SQL操作快照仍为running，步骤为pending/format_repair：这是内部调度器在本地校验失败后留下的待修复标记，**没有对应第二次出站**。外层一次性诊断账本已永久停止，未篡改SQL历史去伪造操作终态；进程已退出、专用PG已停止，禁止将该历史标记作为恢复或修复授权。

私有证据 `/tmp/edumind-p15-d02-recheck-d02` 保存原始请求/响应/HTTP状态、SQLite账本、只读PG快照及规划失败诊断；Git只存去敏摘要/SHA。results-manifest.json绑定私有原件，17项只读结果回归实际通过；命令/XML/SHA见results-validation.json。`backend/.venv/bin/python scripts/check_p15_d02_d02_results.py --check` 预期退出2，准确确认停止与未验证项，不发请求。

中断后恢复的工作仅为证据/文档收尾：已确认这次诊断的Python进程无残留，专用容器exited，停止后新增真实0。没有新Prompt或业务代码修改，不push/merge/部署。T038仍blocked，本路线进入[方案重评](REASSESSMENT.md)，不继续逐例修补、试模型或启动新批次。
