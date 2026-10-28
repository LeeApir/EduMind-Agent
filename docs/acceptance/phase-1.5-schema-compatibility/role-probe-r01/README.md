# T077 / T078 三角色合成协议准入 r01（待批准）

T076完成1eb6963：带type的最小请求严格通过，仅删type的请求匹配400。该观察不证明复杂角色Schema都可用；本包验证头插C原型实际使用的三种完整Schema，准确取舍见[ADR0045 A—C](../../../ADR/0045-role-schema-protocol-admission.md)。当前accepted=false，新增模型调用0。

## 精确适配与样例

| 请求 | 模型/角色与Schema | 唯一类型适配数 | 输出请求上限 |
| --- | --- | --- | --- |
| S1 | DeepSeek官方deepseek-flash/none；C规划PLAN_SCHEMA | 5 | 2048 |
| S2 | 同生成模型；C内容CONTENT_SCHEMA | 1 | 2048 |
| S3 | AIAPI gpt-6.1-sol/low；审核REVIEW_SCHEMA | 4 | 4096 |

schemas.json包含全部原Schema、wire Schema、摘要及准确JSON Pointer。只给已经由字符串enum/const蕴含类型的节点增加type:string，原接受集合不变。所有原长度/数量/uniqueItems/联合类型/开放JSON值和其他约束保留，返回数据仍过原完整Schema；未证实服务支持的关键字不删除。

角色模型/协议一致，**测试消息是通用协议echo，原教学Prompt没有改字节**。S1/S2/S3.json是实际原字节；温度0.2、strict true、stream/store false、无tools。fixture由开发助手手写，非独立人工教学真值；固定内容引用/synthetic，原课程语义校验会拒绝。审核固定unknown及全零占位source_digest，不是模型对真实课程的质量判断。

严格响应校验保留原规则，生成/审核只识别缺省或准确phase=final_answer，原件保留、私有校验视图分离，不以该元数据证明身份。审核允许原有准确system/已知37字符后缀、缺回显记未知及有界summary/成对同UUID元数据隔离，不剥离其他未知字段或放宽Schema。格式/strict/Schema若明确回显不符则拒绝；缺回显记未知，不推断服务端强制保证未来输出。不存在向课程/评分/掌握度接线。

## 准入矩阵与停止

每个完整200响应须符合冻结wire及原Schema、准确echo fixture、来源/模型/用量/元数据门禁，才可进入下一角色；结构正确但echo不同也停止，记录为任务遵从未满足，不能一概称Schema拒绝。任何HTTP/协议/预算/时钟/未知异常即终止，不修改请求补发、不换模型或回退。最多3HTTP，各角色1次，无其他模型/计数/models探测。

三角色全部校验且在窗口内记录成功终态，才protocol_admission_complete=true；若终态超窗，即使已记录3个角色也不能整批准入。缺失/未发送和unknown保留完整3角色分母，不补样、不把未运行叫错误回答。未结束/崩溃目录也不可重启。

这些成功只证明合成上下文的Schema/完整响应协议，不能证明真实课程Prompt/大上下文、学科事实、答案或审核召回。全部准入后才按用户要求准备一份新的头插课程样本：完整正文、确定性代码与答案、4题、动作、sol审核和实际复核；不是把这些echo样例当课程。课程调用和预算仍须另批，未准入不得开始。

## 独立新预算与费用

新登记起300秒含所有本地处理/等待，单HTTP90秒；每目标DNS等待9秒，最多两个固定公网目标，生成两次共用核定IP。请求/响应上限16384/65536字节；输入占额各8192共24576，输出各2048/2048/4096共8192。请求上限与本地报告门禁不是对上游硬界/计费的独立证明。

[DeepSeek公开价格](https://api-docs.deepseek.com/quick_start/pricing/)及[AIAPI公开标价](https://aiapi.world/docs)在2026-10-28核对，精确费率/币种不确定性见pricing.json。取DeepSeek峰时未缓存输入/输出$0.30/$1.20、AIAPI所展示Sol输入/输出$2.5/$15每百万token，按全部占额参考$0.0917504。实际账户币种、费率/缓存/推理/账单、中转完整上下文/路由/留存未知；该参考不是金额硬上限。**本包需新接受实际金额不设硬上限、上游硬界未验证和取消后可能继续计费**，旧窗口/余额/费用例外不继承。

生成专用Key为EDUMIND_DEEPSEEK_COMPAT_API_KEY；审核优先EDUMIND_AIAPI_REVIEW_API_KEY，缺失/空时只在generic Base URL准确AIAPI /v1时借用EDUMIND_PROVIDER_API_KEY。准确批准/新窗口/原字节和一次性目录检查先于读取Key，未批准不检查实际.env内容，不向另一厂商回退。

## 入口、证据和离线结果

```sh
backend/.venv/bin/python scripts/run_p15_role_schema_probe.py --check
# 仅准确批准后：
backend/.venv/bin/python scripts/run_p15_role_schema_probe.py --run
# 纯只读，窗口过期仍可验真：
backend/.venv/bin/python scripts/run_p15_role_schema_probe.py --check-results
```

固定输出/private/tmp/edumind-p15-role-schema-probe-r01，0700/0600，原请求/响应/状态/逐事件摘要链持久保存。Authorization不写证据，任一Key出现在响应时拒绝落盘并终止；real/mock分开，真实结果入口拒绝Mock，摘要重算不信任可改summary。时间核验针对记录值，不是外部可信时间认证。

实际404 passed/0skip：新等价适配/fixture51＋新执行/权限/停止97＋既有相关256（不与历史238重复相加）。严格mypy3源/Ruff通过。反例包括全部角色前置失败、完整Schema保留、假课程语义拒绝、旧scope/预算/凭据目标拒绝、超窗/回退时钟、重算摘要后的绕校验/停止后推进/重复发送、同生成IP、原件/summary/权限篡改、DNS子进程超时回收和不同服务Key绑定。

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_role_schema_contract.py scripts/tests/test_p15_role_schema_probe.py scripts/tests/test_p15_schema_probe_p02.py scripts/tests/test_p15_schema_probe.py scripts/tests/test_p15_schema_audit.py scripts/tests/test_p15_pilot_wire_execution.py -q --tb=short --junitxml=/private/tmp/edumind-p15-t077-full.xml
MYPYPATH=backend:. backend/.venv/bin/mypy --strict --explicit-package-bases --follow-imports=silent scripts/isolated_diagnostics/p15_role_schema_contract.py scripts/isolated_diagnostics/p15_role_schema_probe.py scripts/run_p15_role_schema_probe.py
backend/.venv/bin/ruff check scripts/isolated_diagnostics/p15_role_schema_contract.py scripts/isolated_diagnostics/p15_role_schema_probe.py scripts/run_p15_role_schema_probe.py scripts/tests/test_p15_role_schema_contract.py scripts/tests/test_p15_role_schema_probe.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

旧p01/p02/头插原始实验的冻结源码、原件、unknown及结果不变。本任务只完成零调用准备；准确包和新真实预算需批准，T038 blocked、catalog_only及H封存保持。

准确--check已实际零调用通过；pending --run插桩返回2，在Key/输出前拒绝，真实role-probe-r01目录不存在。当前只完成准备，T078待准确新批准。
