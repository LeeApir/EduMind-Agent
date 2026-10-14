# high 策略两例实际结果

用户批准 2 次 / CNY 0.17 后，执行冻结 `575402d`，同模型 `deepseek-flash` / Responses，
Prompt v3、reasoning=high、最多 8192 总输出 Token、总期限 120 秒。两次真实调用均 HTTP 200、
模型一致、完整结束、审核 schema 有效、用量已知，无重试/回退/修正。

| 历史输入 | 实际审核 | 输入 Token | 总输出 Token | 其中推理 | 耗时 |
| --- | --- | ---: | ---: | ---: | ---: |
| linked-list-concept:explanation:1 | revise，具体 code_safety 问题 | 2741 | 1368 | 1123 | 8.346243 秒 |
| correct-list-concept | pass，issues=[] | 1320 | 229 | 206 | 2.321424 秒 |

第一例实际指出：第二次插入时若 malloc 失败，`push_front` 返回 NULL，`head = push_front(...)`
覆盖原有头指针，使已分配节点不可达，后续 `free_list(head)` 无法释放它们；建议先保存临时返回值。
这与已批准的原缺陷及 code_safety 分类一致，具有具体失败条件、操作和后果，不是泛泛 reject。

第二例的原候选为：

> 链表节点可以分散存储，节点的数据域保存内容，链域保存后继节点地址。理解地址和指针有助于理解链接。

实际回答为 `{"review_version":"resource-review-v3","verdict":"pass","issues":[]}`。
该对照没有被误拒。完整第一例实际问题描述、全部输入/请求/响应 hash 和私有保留证据 hash
见 [strategy-r03.json](strategy-r03.json)。仅保留最终回答和数值用量，未持久化推理正文。

两次合计输入 4061 / 总输出 1597 = **5658 Token**，其中输出内的推理数为 **1329**，不重复相加。
保守费用预留 CNY 0.169712，已知 Token 峰值标价参考 CNY 0.020898，实际账单未知。
SQLite 两条完成记录、无停止错误、无未运行槽；达到批准次数后不再发送。

这是同例策略改善的初步证据；同时更改了推理档位、总输出上限及期限，不能唯一归因为推理开关。
只有两个历史样本，未进行完整四组诊断、正式 50 审核例/100 生成槽或 DSL/T041。
assistant 已按原标签核对具体缺陷，未伪造新的用户人工事实签核。
生产默认仍 none，模式仍 catalog_only。下一步需要实际人工确认及同配置完整诊断的独立预算。
