# T080 / T081 联合类型最小对照 p01（待准确执行批准）

用户已批准6fcb5ef的[ADR0046 A—C](../../../ADR/0046-equivalent-union-schema-proposal.md)离线方案，登记见[批准记录](../../../ADR/0046-approval-20261028.json)。该批准允许准备本包；当前execution-approval.json的accepted=false，**新真实调用0**，不继承任何旧窗口、费用例外或剩余请求。

## 两份准确请求与单变量

仅DeepSeek官方`https://api.deepseek.com/responses` / `deepseek-flash` / reasoning none；温度0.2、strict:true、stream/store:false、无tools。system仅要求合成兼容检查，user固定`Return exactly {"value":null}.`；没有课程、学生、e03真值、H或AIAPI/sol外发。

S1.json（619字节）以anyOf表达value的string/number/boolean/null/array/object；S2.json（564字节）以原type数组表达相同集合。完整外层object、required:value、additionalProperties:false、消息/模型/参数均相同，唯一Schema变化是value节点的等价联合表示。开放数组/对象不增加items/properties/额外约束，不收窄为标量或字符串。离线反向还原后两请求完全相等。

准确JSON必须为`{"value":null}`；结构合法但返回其他值也拒绝。输出通过完整请求Schema；原始响应完整保留，只在私有校验视图识别缺省或准确message.phase=final_answer。其他未知phase、工具、推理、模型/用量/来源规则不放宽。生成不接受编码助手后缀或审核元数据。Schema/strict/format若明确回显矛盾则停止，缺回显记未知；成功不证明服务强制保证所有未来输出或全部类型。

## 顺序、解释与停止

S1只有完整200/准确JSON/Schema/协议/用量/时钟通过并落盘control_validated后，才可预约和发送S2；S1任何异常即终止。S2任何结果都结束，无第三请求、重试、重定向、回退、改Schema补发、换模型、计数/models额外请求或旧批重启。

| 观察 | 预注册结论 |
| --- | --- |
| S1失败 | inconclusive_stopped，S2未运行；不能单凭错误猜anyOf/开放array/object或其他关键字的唯一因果 |
| S1完整通过，S2返回匹配的Schema400 | minimal_union_rejection_observed：该最小上下文中等价表示影响服务接受 |
| S1/S2完整通过 | minimal_union_rejection_not_reproduced：两种最小表示都可用，原复杂内容问题仍未定位 |
| S2其他HTTP/协议/未知失败 | inconclusive_stopped，不把所有400归入同一错误 |

匹配400要求invalid_request_error type/code、param缺省或null、无未知error字段。message准确为：

```text
Invalid json schema: field `type`: unknown variant `array`, expected one of `string`, `number`, `integer`, `boolean`, `null`
```

只可附带规范小写UUID request_id。其他文字/字段差异均保留原件并记不确定。已观察原错误见[角色包结果](../results-role-r01/RESULTS.md)。

CLI返回0只表示两请求对照完整完成（包括预注册拒绝）；返回2表示未完成/异常终止，均不意味着完整角色准入或课程质量。

## 准确新预算与金额边界

新登记起90秒，含DNS和本地处理/等待；单HTTP25秒、DNS9秒，固定同次核定公网IP、Host和TLS SNI。最多2HTTP。每请求输入本地占额4096/总8192；每请求max_output_tokens=32/总64；请求/响应上限1024/65536字节。报告输入/总输出超过单次边界即停；上游硬界未经独立证明，未知占额不退款/重发。

[DeepSeek官方价格](https://api-docs.deepseek.com/quick_start/pricing/)于2026-10-28本轮重读：公开deepseek-flash对应DeepSeek-V4.1-Flash-1017，每百万token峰时输入未缓存$0.30、输出$1.20，非峰时半价。pricing.json冻结缓存/分时明细；按最保守峰时和全部占额参考`(8192*0.30+64*1.20)/1e6 = $0.0025344`。

这是参考而非账单硬上限；实际账户费率/币种、上游输入/输出硬界与账单未独立核实，取消后可能继续计费。**准确执行批准须重新明确接受本批实际金额不设硬上限及这些风险**，旧例外不继承。

## 一次性入口及证据

```sh
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_union_schema_probe.py --check
# 仅本包准确批准后：
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_union_schema_probe.py --run
# 纯只读，过期后仍可验真：
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_union_schema_probe.py --check-results
```

scope固定PHASE-1.5-T081；准确manifest/预算/全部批准标志及有效新窗口先于读取Key或创建输出。只读专用EDUMIND_DEEPSEEK_COMPAT_API_KEY，拒绝借用通用或其他服务Key；不在日志/原件/Git存凭据。固定新目录`/private/tmp/edumind-p15-union-probe-p01`只准一次创建，0700/0600；独占写原请求/响应/状态/逐事件摘要链，任何终态不可逆、不提供恢复接口。响应若含Key则拒绝保存并停止。

只读验真重新核对准确请求/原件/控制/时钟/同IP/来源/响应和summary；Mock不得当真实。成功终态超窗不计完整对照，本机记录时间核验也不是外部时间认证。原p01/p02/role-r01及离线提案均保持冻结。

## 实际离线验证与课程门禁

568 passed/0skip：新最小入口118项＋既有450；严格mypy2源/Ruff通过。覆盖单变量、准确null/其他合法值拒绝、专用Key目标、全部新授权标志、旧scope/离线批准拒绝、第一请求失败停止、两种第二结果、匹配错误严格归类、超时/私网/过大/密钥回显、未知phase、明确矛盾Schema回显、超窗/回退时钟、重算事件后的越序/重复发送/停止后推进、原件/summary/权限/来源篡改、DNS空凭据子进程限时终止回收。测试使用合成Key与Mock，不读取本地真实.env。

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_union_schema_probe.py scripts/tests/test_p15_union_schema_proposal.py scripts/tests/test_p15_role_schema_contract.py scripts/tests/test_p15_role_schema_probe.py scripts/tests/test_p15_schema_probe_p02.py scripts/tests/test_p15_schema_probe.py scripts/tests/test_p15_schema_audit.py scripts/tests/test_p15_pilot_wire_execution.py -q --tb=short --junitxml=/private/tmp/edumind-p15-t080.xml
MYPYPATH=backend:. backend/.venv/bin/mypy --strict --explicit-package-bases --follow-imports=silent scripts/isolated_diagnostics/p15_union_schema_probe.py scripts/run_p15_union_schema_probe.py
backend/.venv/bin/ruff check scripts/isolated_diagnostics/p15_union_schema_probe.py scripts/run_p15_union_schema_probe.py scripts/tests/test_p15_union_schema_probe.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

本包仍只是最小Schema形式的对照，不能证明原复杂内容Schema唯一根因、完整角色或教学可行性。即使观察完成，也须后续独立完整内容/审核角色准入；全部相关角色准入后才准备一份可评课程，课程真实调用另需准确包。T038 blocked/catalog_only/H封存及原教学标准保持。
