# d01执行结果：HTTP200固定OK，旧响应完整性问题仍在

按用户最新“新Key直接调用一次”指令，已且仅已执行一次POST https://www.cbbb.fun/v1/responses，0计数、0重试，未恢复旧r01。授权依据是此明确单次直生成指令与此前已展示的原S1参数；新manifest只用于追溯，未伪造用户对新manifest的独立逐哈希审阅。

| 项目 | 实际观察 |
|---|---|
| HTTP/请求数 | HTTP200；1 HTTP / 1生成请求；无计数 |
| 固定输出 | `{"result":"OK"}`，完整本地Schema校验通过 |
| 模型/推理 | 回执gpt-6-luna / none；不据此证明上游日期快照或新厂商身份 |
| 指令回显 | 原94字符system连接前缀后追加21,336字符；后缀SHA与原p01/r03完全相同：405163336914c9b2b4342e94a5f53acab1ca31f491a9fea8d3755de4c1159225 |
| 输出上限 | 请求16，回显null；reported输出13未越16，但null使参数传递证据仍未决，不断言服务端必然忽略上限 |
| Schema回显更正 | type/name/schema/strict核心字段全部一致。额外`description:null`使运行观察器全对象比较返回false，这是观察器过严，不计作供应商Schema错误 |
| reported usage | input4438 / output13 / total4451，算术一致；输入高于4096本地占额，真实上游限额未获保证 |
| 计数一致性 | 未测试，count_equivalence_tested=false。不得把此前p01计数37与此次reported4438拼成新的同次计数差 |
| 费用/占额 | 实际币种/发票未知；保留4096输入/16输出/本地USD0.01全部unknown占额，不冒充实际费用或可信结算 |

保留执行前冻结源码、7项离线测试、真实回执和运行summary原字节，不通过修改原manifest或源码抹掉Schema假异常。执行后新增独立只读校验，按请求中明确的四个核心格式字段判断；6项离线测试验证description:null可接受、真正核心字段变化拒绝。用户已收到Schema结论更正。此前首次错误报告“Schema回显不一致”不作为本次中转问题证据。

实际HTTP调用完成且能返回固定OK；额外指令和上限回显仍不满足观察契约。按用户此前“仍报错则不使用”的停止规则，当前供应在本轮流程中继续停用；本次单次指令已消费，无后续调用，不计数/重试/改路由/补样本/课程诊断，T038保持blocked。

原件位于 /tmp/edumind-p15-direct-relay-once-d01；SQLite进程关闭后零WAL，只读backup形成DELETE journal一致快照 /tmp/edumind-p15-direct-relay-once-d01-snapshot，私有回执不入Git。可提交的去敏事实及全部SHA见[results.json](results.json)。

```bash
python3 scripts/check_p15_direct_relay_once_results.py --check
# 预期退出2：准确验证响应完整性仍blocked；HTTP调用本身为200
backend/.venv/bin/python -m pytest scripts/tests/test_p15_direct_relay_once_results.py -q
# 6 passed / 0 skipped
```

累计8 HTTP/4生成请求；unknown输入104,192、输出16,048。不把不同币种未知费用汇总为可靠金额，不把单次固定OK当模型教学质量或完整兼容通过。没有教学Prompt/标准/生产设置改动、push/merge或部署。
