# T075 / T076 最小 Schema 兼容 p02（待批准）

前次[结果](../results-p01/RESULTS.md)：S1返回200和符合Schema的合成JSON，但标准message.phase=final_answer触发本项目旧允许字段WIRE_MESSAGE，故S2未发，p01不可恢复。此包只修复新的隔离响应视图，不修改原始Schema、教学Prompt或验收标准；具体范围见[ADR0044 A—C](../../../ADR/0044-synthetic-final-phase-compatibility.md)。批准登记当前accepted=false，新真实请求0。

## 具体改动

新隔离源码p15_schema_probe_p02.py保留p01执行/证据/停止逻辑，精确差异为T076 scope和最终回答phase校验。生成message只新增识别准确`phase="final_answer"`，缺省沿原规则；commentary、显式null、未知值/位置、其他额外字段及原角色/完成状态/Schema/用量/工具门禁保持拒绝。

[OpenAI官方说明](https://developers.openai.com/api/docs/guides/deployment-checklist)定义该最终回答标签；它不是模型身份、真实上下文或教学质量证明。原响应完整存储，phase只在新私有校验副本中分离，其他数据按原validator检查并保存observability，不全量剥离未知字段，不把副本用于续写历史。

已捕获原S1响应SHA `c2e8685b573d316fc924ce5df144f9fcd8534898f24f0560550165e2ec73bd5e`在新视图下离线通过（95/6）；原旧校验仍报WIRE_MESSAGE。该重放不是新实际执行通过，不改旧summary/control/unknown或补发旧S2。旧46文件和所有原件保持摘要一致。

## 准确请求与解释

S1/S2原字节与前次完全相同（581/565字节），二者唯一差异仍为kind.type。DeepSeek官方/responses、deepseek-flash/none、temperature0.2、strict true、max_output_tokens32、stream/store false，纯合成`{"kind":"show_state"}`。只有新S1完整通过才发送新S2；同一次DNS核定、同公网IP/Host/SNI，无课程/学生/e03/sol。

- 新S1失败：不发S2，停止且不确定。
- S1通过、S2匹配缺type/anyOf/$ref的400：仅支持这个最小形式被拒绝。
- S1/S2都有效成功：最小enum-only拒绝未复现，不能认定它是原400根因。
- 其他S2结果/异常：不确定，终止，不增加第三次请求或修改请求补测。

任何结果不自动证明原完整Schema、C角色、审核接口或课程可行性。

## 新独立预算、费用及授权

最多2HTTP，新批准登记起90秒（含本地处理和等待），单HTTP25秒、一次DNS等待9秒，输入/输出本地占额8192/64，单请求输出32；请求/响应上限1024/65536字节。本地占额不是服务端输入硬截，未知不退款/重发。

pricing.json保留2026-10-28核对的[官方价格快照](https://api-docs.deepseek.com/quick_start/pricing/)：峰时未缓存输入$0.30、输出$1.20/百万token，按占额参考$0.0025344。实际账户币种/费率、账单及上游硬限未认证；本批需再次明确接受**实际金额不设硬上限**、未验证输入/输出上界及取消后可能继续计费，p01例外不继承。

专用Key仍为EDUMIND_DEEPSEEK_COMPAT_API_KEY，无回退。准确manifest/新批准/窗口及一次性目录检查在Key/.env、DNS或输出建立之前；固定目录`/private/tmp/edumind-p15-schema-probe-p02`，已有拒绝，无续批。目录0700、文件0600，源请求字节、原始响应/状态和事件摘要链保存，Authorization不记录，含Key响应拒绝落盘。real/mock分开；真实只读入口拒绝Mock来源。

```sh
backend/.venv/bin/python scripts/run_p15_schema_probe_p02.py --check
# 只有准确p02批准后才允许：
backend/.venv/bin/python scripts/run_p15_schema_probe_p02.py --run
# 纯只读，过期仍可验真：
backend/.venv/bin/python scripts/run_p15_schema_probe_p02.py --check-results
```

## 实际离线验证及交接

组合256 passed/0skip：新p02 87＋原p01 71＋审计34＋旧wire64；只计离线工程回归，不与此前238相加，不作为真实教学分子。严格mypy2源/Ruff通过。新87项包含旧全部71项保持断言的新隔离版本回归及16项phase/原S1离线重放/旧scope拒绝；新旧版本分别保留，不改旧断言或期望。

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_schema_probe_p02.py scripts/tests/test_p15_schema_probe.py scripts/tests/test_p15_schema_audit.py scripts/tests/test_p15_pilot_wire_execution.py -q --tb=short --junitxml=/private/tmp/edumind-p15-t075.xml
MYPYPATH=backend:. backend/.venv/bin/mypy --strict --explicit-package-bases --follow-imports=silent scripts/isolated_diagnostics/p15_schema_probe_p02.py scripts/run_p15_schema_probe_p02.py
backend/.venv/bin/ruff check scripts/isolated_diagnostics/p15_schema_probe_p02.py scripts/run_p15_schema_probe_p02.py scripts/tests/test_p15_schema_probe_p02.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

已实际执行新准确包--check通过；pending --run返回2，在Key/输出前拒绝，真实目录不存在；详见根任务日志。T075仅准备，T076真实仍需准确新批准。相关角色准确Schema/响应兼容准入后，下一目标才是一份C链完整可评课程及实际独立复核；本包不准备课程请求、不重启全批、不降低教学标准，T038/catalog_only/H保持。
