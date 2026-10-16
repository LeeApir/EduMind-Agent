# 单例输出预算验证：分散覆盖low，8192实验上限

本包仅使用上次单例诊断的`trace-distributed:candidate`，保留学生材料、原始目标、锚点、v4.4输入、Prompt、JSON Schema、deepseek-flash、low、温度字段0、原pass无附带误报判据和60秒截止。实际请求仅修改`max_output_tokens: 2048 → 8192`；不增加指令、错误日志、示例答案或其他样本。

8192是下一次实验值，不保证足够，也不保证在原超时内完成。官方模型文档声明最大输出384K；Responses把该参数定义为包含思考与可见输出的总上限，因此文档支持8192。此为零调用文档核实，不冒充当前账号/该请求已实测成功。来源：[模型及价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)、[Responses](https://api-docs.deepseek.com/api/create-response/)。2026-10-16 Responses直接读取，中文价格页直读超时后用官方索引核对模型384K/1M及CNY高峰价格；执行当日需重新核对，不一致或不可验证则停。

## 完整预算约束

新入口`run_distributed_budget.py`使用同一个`OUTPUT_LIMIT=8192`生成预算target、请求参数及返回用量上界。准入在Key/DNS/账本之前核对proposal.output_token_limit、价格证明、每条wire.max_output_tokens、逐槽费用和批准总费用的一致性。预算内核也必须接受实际8192请求；不能只改HTTP参数。

| 项目 | 冻结值 |
| --- | --- |
| 实际请求max_output_tokens | 8192（含思考） |
| manifest target.max_total_output_tokens / 输出预留 | 8192 |
| 返回usage.output_tokens检查 | 0至8192，不能减去思考后再比较 |
| Provider文档最大输出 | 384K，高于本实验值；不因此放宽实验上限 |
| 输入保守上界 | 1048576 + 实际wire字节42247 = 1090823token；字节仅作冗余，不是token估算 |
| 高峰未命中单价 | 输入2元/百万token、输出8元/百万token |
| 单次保守预留上限 | **2.247182元**：`2×1090823 + 8×8192 = 2247182`微元 |
| 请求与并发 | 最多1次预留/1次传输尝试、最大活跃1 |
| 超时 | 保留60秒，不随输出上限自动延长 |

预留是保守边界，不是预计账单或Provider账户硬限额。实际缓存、时段和费用以账单为准。未知用量不记0，失败不退款预留。预算内核兼容字段corrections_per_resource固定2不赋予修正调用：本包只有一个probe槽和1次总上限，没有第二槽、correction stage、重试或fallback。

## 完整性与语义质量分别核对

完整性先检查：Provider状态completed、无error/incomplete_details；只有一个assistant消息/可见文本块；严格JSON及原Schema通过；模型和准确wire绑定；用量完整且不超8192。成功到达审核步骤时，将上述检查单独记录到receipt.completeness。响应截断/格式错误仍是完整性失败，不能虚构审核判定。

语义按原学生内容检查：短讲解的过程支持来自代码key_steps（total=2/7/16、i=3退出）和过程题/解析；无需讲解重复所有内容。只审核当前原始目标，不把其他图谱目标当作必达；不能把缺调用示例编造成fact，不能因未承诺动画增加未决。期待pass、五检查ID齐全、findings/unchecked/unresolved均空且无附带误报。合法完整JSON若返回无依据待人工或错误finding，仍不通过该正例判据，完整性成功与质量失败分开记录，原回答不改写。

机器路由/结构信号不能代替实际语义核对；完整回答返回后需阅读材料、意见及锚点形成独立结论，未取得完整回答时语义保持未评定。单次预制正例不是通用质量证明或T040正式通过。

## 独立运行与停止

新包、运行ID、批准、标签绑定及私有目录均独立于旧2048单例与更早运行。旧包、代码、截断结果、未知字段及halt原样保留。旧批准与余额不转入本包。

成功后单槽耗尽；失败持久halt。无论成败只调用一次后停止，不自动提高上限/延长超时/重试或进入其他材料。安全失败诊断仍只留允许的枚举、计数、状态和摘要，不留响应/思考/异常原文或请求头。

本次用户授权零调用准备，不授权发送。requests_authorized=0、fees_authorized=0，无run-approval/labels-human或新真实账本。获得本包准确新单次费用及判据批准后，才能执行唯一真实入口：`backend/.venv/bin/python scripts/run_distributed_budget.py --run-one`。未批准入口须在Key、DNS及新建真实目录之前拒绝。

零调用冻结接口：`backend/.venv/bin/python scripts/prepare_distributed_budget.py --write`。其仅读取凭据文件元数据，拒绝覆盖不同冻结包。本包有效期至2026-10-18 23:59:59（北京时间）；执行日条款/日期门禁保持。
