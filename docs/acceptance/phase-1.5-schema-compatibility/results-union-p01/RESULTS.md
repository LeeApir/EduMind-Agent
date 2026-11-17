# T081 联合表示最小对照 p01：控制失败，未形成对照

**S1 anyOf控制被DeepSeek返回400，本批已终止；S2未发送。** 准确批准6717de3 / manifest `5a62cb5f128719d2583efaeee8c1fc163f480d86f5ab1a4bb316ebaa94de96cf`（78文件），登记见[执行批准](../../../ADR/0046-execution-approval-20261028.json)。

| 请求 | 实际情况 | 结论 |
| --- | --- | --- |
| S1 anyOf控制 | 1 real HTTP；400 invalid_request_error，响应207字节，无usage | 控制未通过，unknown占额1 |
| S2 原type联合 | 未预约/未发送，无请求或响应原件 | 未验证，不能形成单变量对照 |

S1原请求619字节，与准确冻结字节完全相等。未用1请求不继承，无重试、重定向、回退、补样、修Schema补发或旧批续用。没有课程、学生、e03、H或sol调用；没有教学正文/答案，因此也没有新的教学质量结论。

## 原错误与可得结论

```text
Invalid json schema: field `anyOf`: missing field `items` (request_id: 0d24eeaf-f5e2-4cc3-bb4a-b782f0fb4766)
```

S1的value使用anyOf，六个分支依次为string/number/boolean/null/array/object；唯一array分支为`{"type":"array"}`，没有items。该形态保留了原Schema对任意嵌套JSON数组值的开放接受范围。服务错误指出anyOf缺items，但没有返回分支JSON Pointer；`request-comparison.json`列出准确节点及候选分支，不把候选路径当成服务端已证唯一根因。

本次只证明这份准确anyOf控制Schema被该端点拒绝。**不能推断anyOf普遍不支持、添加items就足以解决、object分支和其他关键字都支持，或原复杂内容Schema唯一拒绝点已确定。** 由于控制失败，原type联合S2遵约未发，也不能把T078不同Schema的400拼接成此次受控对照。

本地接受集合等价性不等于服务端Schema子集兼容。本次未删除array/object、收窄为标量、编码为字符串或任意添加items/properties；不以改教学Prompt掩盖接口拒绝。

## 一次性窗口、原件与验证

登记起始：2026-10-28T22:50:57.435926+08:00；截止：2026-10-28T22:52:27.435926+08:00。6条事件约0.40秒内落盘，终态inconclusive_stopped / HTTP_OR_UNEXPECTED_SCHEMA_ERROR；real1/recorded HTTP1/observations0。只读原请求字节、私有文件权限、摘要链、来源/公网目标/Host/SNI、记录窗口及终态重算通过；本机记录时间核验不是外部时间认证。

私有目录`/private/tmp/edumind-p15-union-probe-p01`（0700/0600），逐文件摘要见evidence-manifest.json；Key/Authorization未落盘。无usage，不把拒绝视为已确认零费用；实际账单/费率/币种及上游硬界仍未知。

实际run与check-results均exit2，表示按控制失败停止，不能记为协议通过。实际检查：

```sh
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_union_schema_probe.py --run
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_union_schema_probe.py --check-results
python3 scripts/check_catalog_workflow.py
git diff --check
```

568项离线测试属于T080准备证据，本轮不冒充新增或真实质量分子。原46/47/62/69/78文件冻结及旧结果不变；T081仅完成受控证据交付，完整内容/审核角色与课程前置仍阻塞，T038 blocked/catalog_only/H封存保持。

## 交接

本包不恢复。后续若继续，需要先评估在服务Schema子集中能否等价表示开放递归JSON值，包括items与对象属性边界；不能直接收窄字段来绕过错误，也不能假设补一个items字段就会通过。具体新方案及离线证明完成后，任何新真实探测仍需独立准确包与新窗口/费用授权。当前无新真实授权，不自动补丁、续批或准备课程。
