# T040 历史错误检出首例：漏检后停止

本轮 `deepseek-flash` / Responses 调用正常：HTTP 200、0.934046 秒、结构化 schema 和
完成状态有效、实际输入 2509 / 输出 22 Token。模型对已知含错候选返回：

```json
{"review_version":"resource-review-v3","verdict":"pass","issues":[]}
```

这不是服务不可调用或输出格式错误；本轮审核未检出已批准的具体缺陷。
不能从这一个回答推断模型漏检的唯一内因，也不据此断言所有模型或所有配置都不可用。

冻结历史例为 `linked-list-concept:explanation:1`，原 payload hash
`2725aac9fcdef32bb9afe2ab954cd1255c1aadc847bb583b4462cce06e8da585`。
其 Markdown 第 58–61 行在 `push_front` 分配失败时返回 NULL，第 92–94 行调用者直接覆盖 head：

```c
struct Node *node = malloc(sizeof(struct Node));
if (node == NULL) {
    return NULL;  /* The candidate claims the original list is unchanged. */
}
/* ... */
head = push_front(head, 1);
head = push_front(head, 2);
head = push_front(head, 3);
```

具体失败路径：第一次分配成功，head 非空；第二次或第三次分配失败，返回 NULL；
直接赋值使调用者丢失旧链表唯一的头指针，之后 `free_list(NULL)` 无法释放原节点。
因此“分配失败，原链表不变”的注释没有保证调用者仍可访问原链表。
该缺陷属于原已批准的 code_safety 标签。未执行候选代码。

持久台账已按 `CONCRETE_DEFECT_MISSED` 停止，首组余 4 槽以及其余三组共 8 槽均未发出。
不补发、不跨组挪用预算、不把未运行槽删除，也不合并旧 Qwen 或 T033 成绩。
这不是正式质量的最终百分比分数：正式 50 审核例、100 生成槽和历史生成失败复验均未开始。
本轮自动门禁及 assistant 代码核对不冒充用户人工事实签核。

实际 1/13 请求；保守费用预留 CNY 0.054626，已知 Token 的峰值标价参考 CNY 0.005194，
真实账单未知。重试、回退、修正调用均为 0。生产 `catalog_only` 保持。

51 项离线测试及 Ruff 通过；四组执行清单共 740 次来源文件 SHA 检查通过；
实际请求匹配冻结输入，SQLite 只有一条尝试；私有保留回答中的 JSON 与记录的 review 完全一致。
完整脱敏摘要见 [diagnostic-r01.json](diagnostic-r01.json)，私有回答存于 ignored
`local-materials/phase-1-t040-deepseek-v1/error_detection/`，无请求头、Key 或原始厂商错误落盘。

后续建议先加强对分配失败分支、调用者指针覆盖及资源所有权的审核，再离线验证，
并为修改后的配置冻结独立诊断轮次。旧失败和本轮台账必须保留，剩余额度不能视为新轮次授权。
