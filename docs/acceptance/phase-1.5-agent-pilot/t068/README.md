# T068 隔离协作原型交接

实现规划/示例选择→受限引擎→内容→程序动作→教学审核→最多一次内容修复/重审。使用现有 ProviderGateway 的 StructuredRequest/StructuredResult 和 retry_safe=False，专用适配器只接HTTPX MockTransport；没有真实配置/Key/数据库入口，不继承旧批兼容规则。业务生产文件未改。

角色Schema/引用/精确事实值/规格选择/覆盖/问题身份分别验证；程序创建代码、答案、动作并记录provenance，不把装配字段计为模型首次Schema成功。内容自由文字仍须审核，测试专门证明“事实引用正确但解释矛盾”要由审核发现，程序并不能证明自然语言教学正确。原审核标准 development-scene-review-v2 的全文和摘要保留，原型响应有专用payload Schema，未证明真实服务支持它。

每次调用预约在await前，所有请求/响应、角色、父版本、规格/规则/Prompt摘要、用量及链式审计事件保留。中断/超时/协议异常保留unknown并封闭实例。所有结构错误、事实/安全意见和unknown停，不自动修格式；普通教学revise最多一次内容修复且重审，旧版不覆盖。缺actions会保留静态候选并明确degraded/failed，不调用审核冒充通过。模型pass状态为mock_advisory_pass，始终无独立真值、发布、评分或掌握度资格。

可读开发演示 development-course.md；完整0600原件在 `/private/tmp/edumind-p15-t068-development-r01/{result.json,mock-wire.json,course.md}`。这只是已见合成开发样本，禁止作独立评估分子。输出目录0700且须新建，拒绝已存在目录/符号链接；macOS的/tmp链接也拒绝，使用实际/private/tmp路径。

实际命令（重跑演示要换新输出目录）：

```
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_agent_pilot.py scripts/tests/test_p15_head_insertion_engine.py -q --junitxml=/tmp/edumind-p15-t068.xml
MYPYPATH=backend:. backend/.venv/bin/mypy --strict --explicit-package-bases --follow-imports=silent scripts/isolated_diagnostics/p15_agent_pilot.py scripts/isolated_diagnostics/p15_agent_pilot_mock.py scripts/run_p15_agent_pilot_mock.py
backend/.venv/bin/ruff check scripts/isolated_diagnostics/p15_agent_pilot.py scripts/isolated_diagnostics/p15_agent_pilot_mock.py scripts/run_p15_agent_pilot_mock.py scripts/tests/test_p15_agent_pilot.py
backend/.venv/bin/python scripts/run_p15_agent_pilot_mock.py --output /private/tmp/edumind-p15-t068-development-r01
python3 scripts/check_catalog_workflow.py
git diff --check
```

92 passed、0skip（协作42+引擎50）；类型3源、Ruff/工作流/diff通过；演示exit0，3逻辑Mock调用，真实HTTP0。测试涵盖单次修复/耗尽、事实/安全停止、矛盾说明、缺字段/动作、错误引用/覆盖、问题漂移、准确审核来源/引文、unknown/协议漂移、用量异常、超时/迟到、取消、并发重复进入、预算耗尽、清洗、独占证据/权限/链接拒绝。无PG/C执行，因为无生产接线或数据库行为。

开发中首次mypy使用PYTHONPATH造成包名重复/未解析源码，后以MYPYPATH与explicit-package-bases正确检查；jsonschema沿用项目已有无类型库标注。首个演示路径/tmp被门禁拒绝、无输出，改用/private/tmp后成功。没有通过放宽门禁处理这些情况。

已自查代码与原件：修复前后代码/答案/动作保持相同，新增版本绑定原版本摘要；unknown占用不释放，无自动重发；安全Markdown和代码仅作为数据。T069尚需同条件基线入口、独立材料、真实Provider准确配置/费率/预算与独立授权；本交付不是模型可靠性或多Agent收益证明，不解除T038。
