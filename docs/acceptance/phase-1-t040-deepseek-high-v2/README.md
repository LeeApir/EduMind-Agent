# T040 索引约定修复诊断 r05 提案

当前状态：用户批准预算后按 `d774804` 执行两例。原目标缺陷均具体检出且分类正确，
但第二例审核回答另含不适用于满队列的修正公式，单独质量评估触发 ADMISSION_FAILED 停止。
实际 2 次、13145 Token，余 11 槽未发；索引第三例尚未复验，T040 为 blocked。
见 [结果](results/error-detection-r05.json) 和 [算术反例说明](results/error-detection-r05.md)。
以下保留准备时的修复和预算说明。
原 [r04 漏检及未运行槽](../phase-1-t040-deepseek-high-v1/results/error-detection-r04.md) 保留，
不重新解释标签或将旧成绩填入本轮。

规则：区分自然语言位置与零基索引、访问节点与经过链接、数据头与哨兵头；检查首元素、单节点及端点。
约定缺失且会改变陈述真值时须指出歧义/偏差及边界，不默认 C 的索引规则能解释自然语言“第 i 个”。
当周围代码/文字已明确约定时不要求重复说明，不拒绝正确零基、一基、哨兵或节点访问数陈述。
无按案例 ID 固定 verdict，无预置该例标准答案，无新增本地句式拒绝器；Formal Review schema-v3 不变。

本轮唯一审核配置变化是 Prompt v3 → v4；保留原 13 个历史 payload/参考上下文及顺序、
deepseek-flash / Responses / high / 最大 8192 总输出 / 单次总期限 120 秒（HTTP read 60 秒）。
temperature=0 仍发送，但提供方推理模式不使用该参数，不宣称结果确定。
此前 r03 两例成功属于旧 Prompt，不作 v4 能力通过证据；正式 50 新例及 100 生成槽不作调参输入。

| 独立组及顺序 | 请求上限 | 费用上限 |
| --- | ---: | ---: |
| error_detection | 5 | CNY 0.44 |
| classification，五例再次发送另计费 | 5 | CNY 0.44 |
| correct_control | 1 | CNY 0.09 |
| long_review | 2 | CNY 0.19 |
| 合计，不跨组挪用 | 13 | CNY 1.16 |

按完整 UTF-8 wire 字节加 1024 模板 Token 及包括推理的最大总输出预留，
峰值未命中输入 2 元/M、输出 8 元/M，不靠折扣或缓存，实际账单未知。
原预算不转入；单槽一次、串行，无重试/修正/回退；任一质量/协议/身份/schema/用量/预算失败即停。
前组完整且获实际人工确认后才能进后组，不能将 assistant 判断或预算批准冒充未来事实签核。
本轮不授权正式质量、DSL、T041 或生产切换，none/catalog_only 保持。

[proposal.json](proposal.json) 绑定确切正文、当前源码/锁文件和旧失败证据 SHA，
[requests.json](requests.json) 是 13 个请求。复用可选择独立轮次的组合层，r05 的目录、批准与 SQLite
均独立于旧停止账本；未知轮次标识拒绝，不接受任意路径。

```sh
backend/.venv/bin/python scripts/t040_high_diagnostics.py --round r05 --check-proposal
```

133 项离线测试通过，覆盖审核、代码安全、索引对照、网关/预算/原样 payload 与版本化请求组装；
Ruff、166 源文件严格类型检查、历史批准/冻结样本、活动任务与新提案 hash 均通过。
旧 r04 SQLite 只读核对仍为三条且已停止。测试中的 Mock 回答只验证流程，不能证明模型语义审核已改善。
