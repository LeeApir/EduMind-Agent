# T054：最小计数＋生成兼容性执行包 p01

**待批准，真实请求0。** 本包只有一个合成请求、一次计数、最多一次生成；不含课程、画像、H样本或人工质量标签。不是r03重启或课程r04。用户此前“好”只授权准备，不作为本包准确执行批准。

## 准确范围与预算

| 项目 | 冻结内容 |
| --- | --- |
| 服务／模型 | https://www.cbbb.fun/v1，gpt-6-luna alias，Responses，reasoning none；未知实际快照，不换模型/厂商 |
| 输入 | request.json，两条短合成system＋一条user；要求只返回固定对象 `{"result":"OK"}`，strict闭对象Schema；无工具/历史/文件/联网指令 |
| HTTP | 同一准确body先POST `/responses/input_tokens`，验证计数成功且为1..32000后，才POST `/responses`；最多2HTTP／1生成；无重试/重定向/补样本 |
| 本地占额 | 32,000输入／16总输出，参考费用单位32,016；计数请求本地生成占额为0，但不代表中转对计数免费 |
| 真实token/收费边界 | **未知。** 占额32k/16和请求max_output_tokens=16均不能保证未知中转的实际上界。用户须明确接受单次探索风险，不把本地检查当作上游已强制限制 |
| 时间 | 预约开始40秒墙钟门禁，整个出站过程39秒取消；计数9秒、生成29秒；凭据/公开DNS准备在首次预约和任何dispatch之前。客户端取消不能保证上游停止 |
| 接收 | 每响应最多2MiB本地读取；安全原件、状态、SHA及固定原因先留证；目录0700，新审计文件0600；不保存请求头或异常消息中的凭据 |
| 金额 | 中转币种/收费未知，提案本次不设金额上限，**须新的本包明确费用例外批准**；旧“价格无上限”不继承。若不能接受，保持零调用 |

预算机器文件budget.json区分客户端硬限制、请求参数、unknown占额及无法保证的上游边界，不能把这些数字称为真实费用／token的严格封顶。

## 依据与结果解释

[OpenAI计数说明](https://developers.openai.com/api/docs/guides/token-counting)要求计数使用同一payload并包含结构开销；[输出参数](https://developers.openai.com/api/reference/python/resources/responses/methods/create)定义max_output_tokens包含全部生成token，最小16。本包用这些规范作为预期，不把官方说明当中转实测结果或独立保证。

[ADR0029](../../ADR/0029-synthetic-compatibility-discovery.md)A—C专门提出这一次探索例外。观察核对相等计数、准确指令、回显上限16、Schema/strict及固定输出。额外指令/计数差异/上限null、HTTP错误、坏JSON、超限、凭据回显、超时或未知立即终止，保留完整本地unknown预约，不重试、不退款、不换模型。

若所有可观察项一致，仅报告“本次未观察到契约矛盾”，仍不证明内部上下文真实完整或未来请求硬界，T038不能done，T039/课程生成不开放。若输出16导致不完整，也如实记录，不提高上限后补发。

## 双重批准与执行

`contract-approval.json` 和 `execution-approval.json` **目前均不存在**。两份均须绑定本manifest SHA、batch/purpose、精确limits及人类来源。契约登记须A/B/C；执行登记另须fee_cap_waiver、unverified_upstream_bounds_risk_accepted、no_course_admission全部明确true。它们只依据用户对本准确问题的实际答复登记，不能根据旧批准或本次“好”预造。

唯一真实命令（当前缺批准实际拒绝）：

```sh
backend/.venv/bin/python scripts/run_p15_compatibility_probe.py --execute
```

入口先核对全部源码/材料SHA和双批准，再读.env/公开配置、做SSRF目标审查与IP固定；之后创建唯一输出目录 `/tmp/edumind-p15-compatibility-probe-p01` 及独立SQLite账本，预约后才发送。目录已存在（包括中断）一律拒绝，没有resume/advance入口。原r02/r03账本和T052入口均不改。

任一结果结束该单批次，证据/summary只在私有目录。后续另按真实输出生成只读结果报告，不能把本次准备任务完成当成探针已经执行。具体测试与实际命令见validation.json。

```sh
backend/.venv/bin/python scripts/run_p15_compatibility_probe.py --check
backend/.venv/bin/python -m pytest scripts/tests/test_p15_compatibility_probe.py -q
```

本包准备不执行c01计数提案、不继承任何旧剩余预算或费用例外。正式产品仍catalog_only，无push/merge/部署。
