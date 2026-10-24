# T038：p01 最小真实兼容性探针结果

**未准入，已停止；T038继续blocked。** 用户准确批准f7d620f/ADR0029 A—C、本包费用例外及未验证硬界风险后，仅执行一次同体计数＋生成。实际2次HTTP均200、1次生成，无重试。原r02/r03不重启，未执行c01或课程r04。

## 实际观察

| 项目 | 准确结果 |
| --- | --- |
| 客户端请求 | 549字节纯合成请求；计数/生成两个发送摘要的body SHA均为 `cc45e19ba242760b756bca579ee80e45c6dd93e35c351ed6128a8bef7e459422` |
| 计数 | HTTP200，`response.input_tokens`，37 |
| 生成 | HTTP200，gpt-6-luna，completed；固定 `{"result":"OK"}` 输出满足最小Schema |
| 报告usage | 输入4,438／输出13／总4,451；协议结算仍未验证，实际收费未知 |
| 计数差 | 4,401；服务报告分项 instructions=4,401、text.format=27、items合计10；27＋10＝预计数37 |
| 指令 | 客户端两段system拼接94字符；回执instructions21,430字符，先保留准确前缀，再追加21,336字符 |
| 后缀与r03对照 | 后缀SHA256 `405163336914c9b2b4342e94a5f53acab1ca31f491a9fea8d3755de4c1159225`，与r03逐字相同 |
| 输出参数 | 请求max_output_tokens=16，回执仍为null；输出13小于16不能证明硬限制有效 |
| 拒绝原因 | INSTRUCTIONS_UNVERIFIED、OUTPUT_LIMIT_UNVERIFIED、INPUT_COUNT_MISMATCH；结算前拒绝，模型attempt unknown、全32k/16占额保留 |

## 证据支持的结论

最小的合成输入仍复现额外编码助手模板、计数口径不一致和上限回显缺失；结果不依赖课程材料或复杂课程Schema。本次回执的instructions归因数恰好等于差额，且后缀与r03相同，进一步支持中转／上游转换或回执合成路径没有与计数端保持一致。

这不能证明回执所述文本实际全部进入了模型，也不能判定具体哪一层追加／哪个内部tokenizer错误；分项仍是服务报告。不能把4,401永久补到未来计数，不能据这一次输出13就证明16上限被强制。当前候选没有满足冻结的官方兼容契约，不能恢复课程诊断。

## 授权、账本与验证

原准确manifest SHA256 `160adb246d63464c05abb6e23f110ecbc40ffe20efa3f86e8c6ee4c98065d3f4` 和370文件保持原字节；contract-approval.json/execution-approval.json分别登记用户对ADR A—C及准确执行的同一明确答复，不改冻结提案中的Proposed状态。

原始私有证据保留 `/tmp/edumind-p15-compatibility-probe-p01`，另做关闭一致性快照ledger.snapshot.sqlite；Git只收metadata/SHA、批准、报告和只读checker。继承T052的audit格式version含offline字样，指的是旧格式名；本次生产者为获准的新探索执行器，实际底层为HTTPX AsyncHTTPTransport，不是Mock。两个200状态在收到时实际持久化，未回填旧r02/r03的未知HTTP状态。

- `python3 scripts/check_p15_compatibility_probe_results.py --check`：预期退出2，准确验证blocked、两次同体/状态/原件、双批准绑定、快照unknown、后缀与累计计数。
- `backend/.venv/bin/python -m pytest scripts/tests/test_p15_compatibility_probe_results.py -q --junitxml=/tmp/edumind-p15-p01-results-r01.xml`：9 passed、0 skipped；只读正例、假pass/退款/零费用/T038假done/隐藏旧批次/伪计数/篡改风险批准/WAL拒绝。
- 原r02/r03结果checker仍预期退出2；新包--check、Ruff2、工作流及diff通过，详细证据见validation.json。

## 停止与交接

本批模型unknown占额32,000输入／16输出，不以已报告的4,438/13自动释放。连同原r02/r03，累计6 HTTP／3生成，unknown合计96,000输入／16,016输出；未生成教学场景、没有任何自然质量或审核评分、没有生产开放。

本次准确授权已消耗，目录存在使重启直接拒绝；不复用余量，不追加探针/修复后重试/换模型/Provider。下一步只能由用户决定服务商修正请求转换／计量／参数映射，或另行提出准确替代候选与执行方案。本次不继续调用、不push/merge/部署；保存无Task-Completed的本地进度提交，T039不领取。
