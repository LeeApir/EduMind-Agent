# T073 / T074 最小 Schema 确认包 p01（待批准）

本包独立于已停止的头插p01。T072离线审计完成e84ab53，准确两处enum-only及其他边界见[审计](../audit-r01/README.md)。当前批准登记accepted=false，真实新增0；具体新边界见[ADR0043 A—C](../../../ADR/0043-minimal-schema-discriminator-probe.md)。旧费用例外、窗口、样本和剩余额度不继承。

## 准确请求与解释

S1/S2.json是实际发送原字节，均为合成单字段kind，DeepSeek官方/responses、deepseek-flash/none、temperature0.2、strict=true、stream/store=false、max_output_tokens32。S1有kind.type=string；S2唯一差异是删除该type。只有S1通过严格响应及准确JSON/用量检查后才发S2；同次DNS子进程核定（空环境、固定域名、超时终止回收）、同公网IP和Host/SNI，无工具/课程/私有真值/sol。

| 观察 | 本批结论 |
| --- | --- |
| S1失败 | 不发S2；inconclusive_stopped。 |
| S1通过，S2匹配缺discriminator的400 | minimal_enum_rejection_observed；仅支持这个最小形式被拒绝。 |
| 两者有效成功 | minimal_enum_rejection_not_reproduced；不能继续认定enum-only是原400根因。 |
| S2其他响应/异常/越界 | 不确定并终止，unknown保留。 |

每个结论均终止本批，没有第三请求或适应性补测。响应未定位原复杂Schema的子节点，两次观察不证明原完整Schema、C角色或课程可行性。

## 预算与凭据

最多2HTTP、新批准登记起90秒；单HTTP25秒、一次DNS最多9秒；输入本地占额8192、总输出占额64，单次请求输出32；请求/响应≤1024/65536字节。输入占额不是已验证的服务端硬限，未知发送/协议/用量不释放次数。超时和取消后实际计费仍可能继续。

[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)于2026-10-28核对：每百万token，缓存输入$0.003/$0.006、未缓存$0.15/$0.30、输出$0.60/$1.20（低峰/峰时）。按占额取峰时未缓存参考$0.0025344，完整登记见pricing.json。实际账户费率/币种/收费未认证，不能把参考数当硬上限；本次待明确批准**实际金额不设硬上限**和未验证上游限制风险，旧豁免不沿用。

唯一专用环境变量EDUMIND_DEEPSEEK_COMPAT_API_KEY；不读取其他服务Key、不回退。准确包/新批准及窗口通过、且输出目录不存在后才读取Key/.env。当前没有读取。

## 运行与证据

```sh
backend/.venv/bin/python scripts/run_p15_schema_probe.py --check
# 准确批准登记后才允许：
backend/.venv/bin/python scripts/run_p15_schema_probe.py --run
# 纯只读，窗口到期仍可核验，不继续发送：
backend/.venv/bin/python scripts/run_p15_schema_probe.py --check-results
```

固定输出`/private/tmp/edumind-p15-schema-probe-p01`，仅一次新建；已有、崩溃、中断或终止均不能重启。目录0700/文件0600。逐事件先验证再独占持久化，保留源字节和链摘要；独立读取器重算S1有效控制、唯一发送、同IP、窗口和S2观察，拒绝重算摘要后的越窗/绕控制/stop后推进、原件/summary篡改。原始响应含Key不落盘，Authorization不记录。

传输事件区分real/mock；真实结果入口拒绝Mock证据，不把离线成功当真实请求。

event sent仅是客户端dispatch标记，不是服务执行/账单证明。实际invoice/currency固定未知；可信响应的reported usage单独保存，HTTP400/超时无usage保持unknown，不能写成零收费。窗口按本机数值核验，不冒充外部时间认证。

## 离线验证与后续门禁

实际组合回归169 passed、0skip：新探针71＋T072审计34＋复用wire64；不是169次真实调用，也不与旧238离线重复相加。严格mypy2源、Ruff通过。命令：

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_schema_probe.py scripts/tests/test_p15_schema_audit.py scripts/tests/test_p15_pilot_wire_execution.py -q --tb=short --junitxml=/private/tmp/edumind-p15-t073-combined.xml
MYPYPATH=backend:. backend/.venv/bin/mypy --strict --explicit-package-bases --follow-imports=silent scripts/isolated_diagnostics/p15_schema_probe.py scripts/run_p15_schema_probe.py
backend/.venv/bin/ruff check scripts/isolated_diagnostics/p15_schema_probe.py scripts/run_p15_schema_probe.py scripts/tests/test_p15_schema_probe.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

这是待批的新最小实验，未应用T072的完整Schema副本，未修Prompt/课程链。后续课程可行性按用户顺序执行：先补足相关角色准确wire Schema兼容证据，再准备单个新支持槽C规划→内容/确定性代码答案动作→sol审核及独立实际复核的一份完整课程；不恢复28臂槽或T038全套。教学门槛、catalog_only和H封存保持。

准确包已实际零调用--check通过；pending --run返回2/EXACT_NEW_APPROVAL_REQUIRED，插桩确认未读取凭据、未建立真实输出。所有测试使用Mock或伪DNS进程，无真实Provider/DNS探测。T073完成只代表准备完成，T074仍待准确批准。
