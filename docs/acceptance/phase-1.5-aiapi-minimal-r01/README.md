# AIAPI gpt-6.1-sol 最小执行包 r01

本包依据用户本轮原话“准备可审查的最小执行包，写清请求、次数、模型和费用上限，再按该包实测……直接执行，不用我批准”准备并执行。不声明用户逐文件/逐哈希人工审阅，不生成虚假的人工签核。归属T038的独立合成兼容观察，T038保持blocked；不属于课程质量验收。

## 准确范围

- 端点：仅 `POST https://aiapi.world/v1/responses`，请求模型仅 `gpt-6.1-sol`，reasoning=none、service_tier=default、store=false。
- 凭据：根.env的EDUMIND_PROVIDER_API_KEY；只核对Base URL是aiapi.world，可显式指定本包模型但不改.env。
- S1：[准确请求](S1.json)，顶层教学角色instructions、严格JSON Schema，返回角色标记/一句栈解释/未知画像null。非流式，请求输出上限128。
- S2：[准确请求](S2.json)，复用现有free_course_planning的Prompt和完整Schema，唯一合成目标是5分钟栈入门，[准确输入](S2-inputs.json)。流式，请求输出上限512。生产规划器原8000输出上限在此明确缩减为512，这是兼容探针，不能作为完整规划质量验收。
- 最多2次HTTP/2次生成，串行，无计数/重试/回退/重定向；整批90秒，每次curl40秒，最多1MiB响应。只使用合成数据，不写数据库/调用Worker/执行模型代码。
- S1全部检查通过才发S2。任一请求/解析/完整性失败即停；上限null、缺失或不同属于上限未证实，立即停止，不直接断言服务端忽略参数。超时/未知/异常整槽保留unknown，不补发。

## 费用与可执行边界

本地规划支出限额为USD **0.05**：S1留额0.015、S2留额0.035。输入规划占额4096+8192，输出请求128+512。按2026-10-26商家公开页输入$2.5/M、输出$15/M包络，规划金额0.04032美元，小于本地总额；缓存不打折，且不继承旧余额。公开来源：https://aiapi.world/pricing 。该页展示价格不证明此Key/分组最终费率。

**这是本地预约上限，不是平台账单硬限。** 未知额外输入、供应商实际币种/费率、忽略输出参数和客户端断开后计费均未被排除。actual_invoice_hard_cap_usd和actual_invoice_usd保持null，不伪造封顶或零费用。每次出站前持久记录整槽预约；有usage仍不退回未知收费占额。必须绝对账单封顶时需要服务商限额证据，本包不作该保证。

## 执行与留证

```bash
backend/.venv/bin/python -m pytest scripts/tests/test_p15_aiapi_minimal_r01.py -q
backend/.venv/bin/ruff check scripts/run_p15_aiapi_minimal_r01.py scripts/tests/test_p15_aiapi_minimal_r01.py
backend/.venv/bin/python scripts/run_p15_aiapi_minimal_r01.py
backend/.venv/bin/python scripts/run_p15_aiapi_minimal_r01.py --execute
```

无参数只校验SHA/Schema，不读密钥或联网。--execute先验证冻结manifest，再独占创建/tmp/edumind-p15-aiapi-minimal-r01；已有目录即拒绝，不支持恢复。出站采用已测可连通的curl，故不宣称生产HTTPX客户端兼容通过。密钥通过0600临时文件传入，路径不包含密钥，临时目录退出删除。加密推理及账户关联字段从持久回执中省略；保留请求ID、结构、usage和输入/输出上限回显。

退出2表示观察失败或未证实，退出0最多表示最小观察通过；两者都不解除catalog_only、T038或旧验收阻塞。S2没有运行不得算通过；正文通过但参数未证实分开记录。真实结果见results.json，离线证据见validation.json。旧材料保持原字节，无push/merge/部署。
