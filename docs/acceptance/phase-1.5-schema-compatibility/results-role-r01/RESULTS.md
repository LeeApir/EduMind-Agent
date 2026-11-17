# T078 三角色合成协议 r01：内容Schema拒绝，批次停止

本次只完成准确受控采集，**三角色协议准入未通过，不进入课程验证**。准确批准d440822 / ADR0045 A—C；manifest `12168a9918f234b467cf94800b2fd5177f4ac4a47ca8d637642d12e0307f8e02`（62文件），批准登记见[ADR0045登记](../../../ADR/0045-approval-20261028.json)。

| 角色 | 实际结果 | 结论 |
| --- | --- | --- |
| S1 C规划 / DeepSeek官方deepseek-flash/none | HTTP200/completed；原样fixture、原完整Schema、模型/用量/phase通过；准确Schema回显；报告输入614/输出119/推理0 | 合成规划协议准入 |
| S2 C内容 / 同模型 | HTTP400 invalid_request_error，无usage | 内容角色未准入；保留unknown占额1 |
| S3 审核 / AIAPI gpt-6.1-sol/low | 未发送，无该服务DNS或HTTP | 未验证；不登记通过或模型错误 |

本批2 real HTTP，无重试/回退/补发；原S1/S2请求体分别2377/2870字节且与冻结原字节相等；响应3091/274字节，均在界内。三角色分母保持3，准入1，未运行1。实际S1报733 total token，不能推断S2无计费；实际账单/币种未知，未用第三请求及剩余窗口不继承。

## 原始拒绝与证据边界

S2完整错误消息：

```text
Invalid json schema: field `type`: unknown variant `array`, expected one of `string`, `number`, `integer`, `boolean`, `null` (request_id: b579628d-5c5e-4d1b-8fda-beef77c65062)
```

该错误来自DeepSeek官方内容Schema请求，尚未到达生成课程或sol审核。它没有给出JSON Pointer，**不能据此说所有array都不支持，或断言某个具体字段是唯一根因**。S1准确Schema含5个单值type:array且已被接受；S2另含两个相同的开放fact_refs值类型联合：

- `/text/format/schema/properties/paragraphs/items/properties/fact_refs/items/properties/value/type`
- `/text/format/schema/properties/questions/items/properties/fact_refs/items/properties/value/type`

两者均为 `["string","number","boolean","null","array","object"]`。因此“该位置的类型联合不接受array/object”是与证据相符的后续候选解释，**不是受控单变量因果结论**。S1/S2本来是不同角色的完整Schema，不能把它们当成只差上述字段的对照。`schema-type-inventory.json`完整列出两请求array及联合type位置；现有所有约束仍保留，未投影为标量、删字段或改课程Prompt。

原生Draft202012本地合法与服务端子集准入不同。此前最小enum-only拒绝已经由独立S1/S2单变量观察确认；此次字符串literal等价显式化足以让规划角色通过，但未解决内容角色的全部兼容问题。未发现教学内容或答案错误，因为本次没有生成教学课程。

## 窗口、来源与原件

登记起始：2026-10-28T22:21:14.771810+08:00；截止：2026-10-28T22:26:14.771810+08:00。全部11条事件约1.46秒内写入，终态inconclusive_stopped / ROLE_HTTP_STATUS。生成两请求复用同次核定公网目标/Host/SNI；来源real2，完整原件/事件摘要链/请求原字节/状态/响应摘要/逐槽本地校验及记录时钟重算通过。本机记录时间核验不是外部可信时间认证；服务Schema回显也不证明所有未来输出由服务强制保证。

私有原件目录 `/private/tmp/edumind-p15-role-schema-probe-r01`（目录0700、文件0600）；逐文件摘要见evidence-manifest.json。Authorization未落盘；公开结果仅保留合成事实与脱敏错误，不提交Key/.env。旧p01/p02原件、冻结包与结果不变。

## 实际验证与交接

```sh
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_role_schema_probe.py --run
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_role_schema_probe.py --check-results
python3 scripts/check_catalog_workflow.py
git diff --check
```

run/check-results均返回2，表示已按异常条件停止及协议未准入，**不是执行器异常或通过**；只读evidence_verified/recorded_window_verified为true。404项离线测试是T077证据，本轮不冒充新增或真实质量分子。T078仅完成受控验证交付，后续课程前置仍阻塞；T038 blocked/catalog_only/H封存保持。

下一步只能先离线提出“保留原接受集合、如何表达开放JSON值及联合类型”的具体兼容方案与反例。若需确认远端因果，应另建独立最小单变量包并获新准确授权；不续本批、不自动删约束补发、不跳过内容或审核角色，也不准备/发送课程。
