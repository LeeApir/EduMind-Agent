# T040 r02：审核指令修复后同例仍漏检

用户同意独立 13 次 / CNY 0.69 诊断预算后，以 `2fc9e6a` 冻结执行。
首例 `linked-list-concept:explanation:1` 的候选和上下文与 r01 相同，仅审核指令升级为 v3。
`deepseek-flash` / Responses / reasoning=none 正常 HTTP 200 返回，0.819711 秒，
输入 2716 / 输出 22 Token；完成状态、模型和 JSON schema 均有效。
实际审核回答仍为：

```json
{"review_version":"resource-review-v3","verdict":"pass","issues":[]}
```

原已批准缺陷仍存在：第一次分配成功，链表 head 非空；后续 `push_front` 分配失败返回 NULL，
调用者直接赋值给 head，丢失旧链表头，随后 `free_list(NULL)` 无法释放原节点。
代码位置为原 Markdown 第 58–61、92–94 行。未执行候选代码。
失败路径、原输入 hash、请求/响应及保留回答 hash 见 [脱敏结果](diagnostic-r02.json)。

| 独立轮次 | 指令 | 首例实际结论 | 门禁 |
| --- | --- | --- | --- |
| r01 | instructions-v2 | pass，无问题 | 漏检，停止 |
| r02 | instructions-v3 | pass，无问题 | 漏检，停止 |

这里只比较同例观测，不合并不同配置的质量分数，不推断模型在其他配置或任务上的表现。
现有证据只能证明这次指令修改没有修复该例；不能由两个 pass 回答定位模型漏检的唯一内因。
前序 94 项离线测试、Ruff、166 源文件类型检查通过，不等于模型语义质量通过。

r02 持久台账已 `CONCRETE_DEFECT_MISSED` 停止；首组余 4 槽和其余三组共 8 槽均未发出。
本轮预留 CNY 0.056960，已知 Token 的峰值标价参考 CNY 0.005608，实际账单未知。
两轮仅作账务汇总：2 次、5269 Token、保守预留合计 CNY 0.111586。
无重试、回退、修正调用，不把剩余额度视为新轮次授权。

核对四组当前执行清单共 752 次来源文件 SHA、实际请求、SQLite 及私有保留回答的 review 一致；
旧 r01 的 185 份源码按 `2f989da` 历史提交核验，旧 SQLite 只读核对仍为 1 次且已停止。
assistant 核对与已批准历史标签没有被冒充为新的用户人工事实签核。

T040 未完成，正式质量/DSL/T041 未启动，生产 `catalog_only` 保持。
后续需先决定不同审核/推理策略及具体有界对照方案，再独立冻结授权；不直接重复同类 Prompt 补丁和付费重放。
