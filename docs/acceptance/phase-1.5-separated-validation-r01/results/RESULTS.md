# T088：W4 输出 Schema 与非法尾部，六次请求后停止

**真实发送 6 HTTP，P0、W0–W3 严格通过；W4 HTTP200但返回 Schema 且末尾多一个 `}`，严格 JSON 解析失败，全批停止。R0 未预约、未发送，没有修复结果或待签核的真实改写。** 本批剩余1请求失效，不重试、补样、重启或延长窗口。

准确准备提交 `588b0acbcb0940f4dbb7500fe87401f637a7b6e4`；[175文件 manifest](../manifest.json) SHA256：`0c74b3751bdfd1dfffe7cfc3aa56bd30257e4ec850f18d80041b78bea401a1e3`。七请求、Schema、strict、本地校验、顺序和停止规则保持原样。[本次执行批准及费用例外](../execution-approval.json)登记用户直接指令，不继承旧授权。新窗口为2026-10-29T14:44:12.903292+08:00至14:59:12.903292+08:00；运行在14:44:26.504115+08:00终止，控制器单调计时约11.853秒。

| 用例 | 结果 | 响应自报输入/输出 token | 完整输出 |
| --- | --- | ---: | --- |
| P0 纯协议回显 | HTTP200，严格检查及精确回显通过 | 1385 / 265 | [P0](output-texts/P0.txt) |
| W0 空包装 | 同上 | 1391 / 265 | [W0](output-texts/W0.txt) |
| W1 protocol_stage | 同上 | 1400 / 265 | [W1](output-texts/W1.txt) |
| W2 original | 同上 | 1656 / 265 | [W2](output-texts/W2.txt) |
| W3 issues | 同上 | 1437 / 265 | [W3](output-texts/W3.txt) |
| W4 original_input | HTTP200，非法 JSON，立即停止 | 2277 / 1031 | [W4 原文](output-texts/W4.txt) |
| R0 实际措辞修复 | 未预约、未发送、无输出 | N/A | 未运行 |

前五个输出的值都等于准确 expected_output，digest 相同。它们只证明这五个准确请求本次回显合格，不证明模型能独立解题或修复教学内容。`repair_success`、`diagnostic_success`、`full_role_admission_complete`均为false；R0为`not_run`，独立语义复核未进行。若未来有R0机械通过，仍须独立语义复核，不能据本次前五槽推定成功。

## W4 的准确失败与结论边界

原始文本3306字符/字节，SHA256 `313427b759a5a21a57b31e909a7d77592631fcdbd37d57866f61b0b3f4a68e5b`。严格解析错误：

```text
JSONDecodeError: Extra data: line 1 column 3306 (char 3305)
```

只读诊断的raw_decode解析前3305字符，得到的对象逐值等于本请求**完整输出Schema**；余下恰好是`}`。这项诊断未用于准入；截掉尾部后仍是Schema而非目标实例，也不能通过原完整校验。没有修括号、裁对象、删字段或重新发送。

外层status=completed、error/incomplete_details=null、reasoning=none、phase=final_answer，Schema回显准确；报告输出1031小于请求4096。没有证据表明是请求输出上限截断；strict:true或Schema回显准确也未确保实例内容有效。

W0与W4的预注册唯一增量为`/role_input/original_input`固定内容块。W0本次通过，W4本次失败，因此记录该包装条件下的关联；每例仅一次，整块增删同时影响长度/内容，**不能唯一归因某句话、采样、模型或服务实现，也不能给出稳定失败率或因果证明**。R0是不同任务且未运行，不参与该对照。与T085 S5属于同类“返回Schema且JSON非法”错误，但字节不同：旧前缀缺根type、尾部为`, "type": "object"}`；本次前缀为完整Schema、尾部只有`}`。

## 全量证据、预算及验真

- [只读汇总](assessment.json)：由冻结控制器从原件重算，6 real/6响应/5 validated/1协议未可信/1未运行；不是兼容成功。
- [逐响应观察](response-observations.json)、[失败分析](failure-analysis.json)：包括全部自报用量、原文长度/摘要与准确解析位置，所有6份合成输出完整导出，无传输ID。
- [原件清单](evidence-manifest.json)：51份原件（31事件、6请求、6状态、6完整响应、grant、summary）的完整路径/字节/权限/哈希。原件保留在`/private/tmp/edumind-p15-separated-validation-r01`，目录0700、文件0600；请求不含Authorization，Key未落盘。完整信封可按清单直接读取，没有删改原始响应。
- [只读与防重启证据](readonly-verification.json)、[结果清单](result-manifest.json)、[验证记录](verification.txt)。`--run`及`--check-results`均exit2，终态`inconclusive_stopped`、原因`STRICT_JSON_INVALID`；31事件/来源IP/请求/窗口/原件/摘要通过只读核对。停止后用禁止Key/DNS/socket的陷阱调用前置门禁，exit2拒绝已有目录，51原件摘要不变；没有新增出站请求。

批准上限7HTTP/900秒、输入占额57344/总输出请求上限28672、单HTTP60秒/DNS9秒、请求65536/响应262144字节。实际预约6次占额49152/24576；已发W4的协议失败占额保留，不退款重发；未用1次与剩余窗口均不自动转新批。

全部六响应自报输入9546、输出2356（其中推理0），合计11902；前五合格槽自报输入7269、输出1325；自报缓存输入6144。它们不是账单或服务硬限认证。公开费率/参考预算保持冻结，实际费用/币种与上游限额未独立核实；用户明确接受的例外只适用于本准确批次，不产生后续授权。

## 交接

T088仅完成一次获准证据采集和合规停止，不表示诊断成功或整套角色准入。整套接口与课程实验门禁仍未解除，T038 blocked、catalog_only、H封存和正式教学标准保持。本轮不继续修Schema/Prompt、不启动课程或新验证包。交回全部证据，等待评估助手/用户审查。

只读复现（不会读取Key或发起HTTP；需要保留本机私有原件）：

```sh
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_separated_probe.py --check-results
PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-separated-validation-r01/results/check_evidence.py
```

前一命令预期exit2为已停止的真实结果；后一命令exit0仅表示证据核对通过。
