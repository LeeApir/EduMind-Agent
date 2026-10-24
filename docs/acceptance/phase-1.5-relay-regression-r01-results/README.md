# 新.env中转原故障复测：计数HTTP404，按约定停止使用

用户在准确包8fce9e7交付后回复“批准”；ADR0031 A—C、manifest `2c379b62b70dbc0d99e9534558e5c3e67edd6403f698c39582997ae1bb8fc9c2`、未知收费/上游限额风险和失败弃用规则已独立登记在原包的 contract-approval.json、execution-approval.json。冻结原件402 SHA不改，批准不继承官方或旧p01。

只执行一次 `backend/.venv/bin/python scripts/run_p15_relay_regression.py --execute`，退出2：

| 事实 | 本次结果 |
|---|---|
| 当前准确供应 | .env https://www.cbbb.fun，显式映射/v1；gpt-6-luna/Responses/none/default |
| 计数接口 | POST /v1/responses/input_tokens 返回HTTP404，无有效input_tokens |
| 真实出站 | 1次HTTP计数请求；0次生成；没有重试、改路径或后续探测 |
| 批次/结果 | stopped/provider_contract_failure；candidate_rejected_stop_using |
| 教学/兼容结论 | 原计数差/追加指令/输出上限三项均未进入生成观察；保持未验证，不登记修复、复现或通过 |
| 本地预约 | count/model两笔均unknown，模型未dispatch；保留4096输入/16输出/8208 USD规划micros，不退款 |
| 实际收费 | 币种、费率、发票均未知；本地规划额不证明实际费用或服务端硬限 |
| 累计 | 7 HTTP/3生成；旧unknown96,000/16,016＋本次4096/16＝100,096输入/16,032输出 |

404是当前准确计数请求的失败证据，具体原因可能涉及服务端路由、接口支持或权限，尚未独立定位；生成接口本次未调用。按用户“如果还是报错不使用这个中转”的停止规则，该供应配置在本轮流程中弃用，不再改路径、换模型或补请求，T038保持blocked，不解锁课程诊断、T039或生产开放。.env保留用户配置，不修改教学Prompt/阈值。

原始私有响应、SQLite和收据位于 `/tmp/edumind-p15-relay-regression-r01`；进程退出后WAL为0，使用SQLite只读backup创建DELETE journal的一致快照 `/tmp/edumind-p15-relay-regression-r01-snapshot`，不把SHM协调文件当数据库证据。首次材料收集误将非零SHM视为异常，未写结果或执行任何请求；随后依据零WAL与只读backup完成一致快照，未改变原运行账本。只提交[脱敏metadata及SHA](results.json)，原件不入Git。snapshot ledger与原ledger因journal模式不同，文件SHA分别保存。

共享runner summary中 local_accounting.requests=2 是预约数，不是HTTP次数；fee_units_are_conservative_not_invoice是该runner的内部字段，在未知供应价格下不能据此声称覆盖实际收费。最终 assessment明确标记 unvalidated_planning_allowance=true，actual_invoice=null；实际HTTP=1、模型=0。未知model预约不代表模型已发送。

只读校验：

```bash
python3 scripts/check_p15_relay_regression_results.py --check
# 预期退出2：准确验证blocked，禁止将2改成“通过兼容”
backend/.venv/bin/python -m pytest scripts/tests/test_p15_relay_regression_results.py -q
# 9 passed / 0 skipped；禁止网络或.env读取
```

原件/快照丢失或哈希、批准风险、HTTP、预约状态、历史累计被篡改时拒绝核验。核验缺失不授权再次执行。后续无剩余可用请求；旧批次、官方包或其他供应不会自动执行。当前只保存进度，不创建T038完成提交，不push/merge/部署。
