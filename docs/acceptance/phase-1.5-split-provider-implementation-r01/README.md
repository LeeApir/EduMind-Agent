# ADR-0033 隔离双供应实现交接

2026-10-27：[批准登记](../../ADR/0033-approval-20261027.json)接受 A—C、E 的隔离实现；D 的真实输入/输出边界门禁保留。主任务 PHASE-1.5-T038 仍 blocked。本包真实 Provider 调用为 **0**，没有生产切换、课程诊断、旧批次重启或付费授权。

## 交付行为

- 按准确 stage 和完整 Schema SHA 路由：DeepSeek 官方 Flash 生成，AIAPI sol 审核。入口只接受显式 HTTPX MockTransport 和 TEST_ONLY 凭据，不读取环境密钥；路由、凭据或传输对象被运行时替换即拒绝。
- 从真实隔离 PostgreSQL 读取 owner 私有课程、准确计划/版本、完整场景与必要上游；发送前后校验来源。审核包括私有答案和受约束动作，不包含 gold、期望标签、真实学生或 H01–H08。原生成和旧探针 Prompt/Schema 不变。
- 持久记录预约、发送、响应、usage 与合成计费占额；未知结果不重发，不自动回退。并发预约、分角色/课程/全局预算与墙钟门禁受测试覆盖。所有 usage 和参考费用均为 Mock，不是实际账单或真实供应商上界证明。
- 每个冻结场景最多一次意见，校验完整 Schema、准确引用和来源绑定。非 pass 暂停；人工误报裁定绑定原意见与来源，保留原判定，不自动恢复。严重/未决问题停止。原逐槽人工检查及新场景审计摘要同时存在才可推进。
- 使用已有调度器和仓储，未更改 backend/app、生产模型配置、教学阈值或审核发布规则。课程保持未签核草稿。

## 验证

最终源码：**42 项离线 + 5 项真实隔离 PG/HTTPX Mock = 47 passed，0 skipped**。逐项计数、XML 路径和 SHA 见 [validation.json](validation.json)，代码及材料 SHA 见 [manifest.json](manifest.json)。重复运行不累计通过数。

第一次 PG 运行暴露计划持久化 candidate 包装读取遗漏，已修复。第二次的两个对抗设置被数据库不可变约束正确拒绝，测试现验证该拒绝，并额外覆盖合法前移 head 导致旧来源失效；没有禁用约束或修改产品存储逻辑。后续最终 5 项全部通过。原有 Starlette/anyio 弃用警告仍存在。

PG 测试使用专用 test-only 容器、回环 15437 和新数据库；容器原为 exited，执行后已恢复 exited。临时 XML、数据库均保留，Git 只保存脱敏计数与摘要。测试适配器中 true 的输出界与常数输入界仅对应固定 Mock usage；隔离运行适配器始终返回 bounded_output_verified=false，不能当作供应商证据。

```sh
backend/.venv/bin/python -m pytest scripts/tests/test_p15_split_provider.py scripts/tests/test_p15_split_provider_design.py -q --junitxml=/tmp/edumind-p15-split-unit-final.xml
backend/.venv/bin/python scripts/check_p15_split_provider_implementation.py --check
backend/.venv/bin/python scripts/check_p15_split_provider_implementation.py --execute
```

最后一条预期退出码 **2**，在凭据、DNS、数据库或真实出站之前拒绝 D 门禁。PG 的实际执行采用下列等价辅助脚本（容器已启动时运行；脚本不启动或停止容器），最终运行数据库后缀为 2aff4f62：

```python
import subprocess, sys
from pathlib import Path
from uuid import uuid4
root = Path.cwd()
sys.path.insert(0, str(root / "scripts"))
import run_catalog_db_tests as db
# Existing helper enforces the test-only label and loopback binding.
db.CONTAINER = "edumind-phase1-t037-pg"
env = db.test_environment("edumind_catalog_p15_t020_split_" + uuid4().hex[:8])
for key in list(env):
    if key.startswith(("EDUMIND_PROVIDER", "EDUMIND_REVIEW_CANDIDATE", "EDUMIND_DEEPSEEK", "EDUMIND_AIAPI", "OPENAI_", "ANTHROPIC_")):
        del env[key]
subprocess.run([str(root / "backend/.venv/bin/python"), "-m", "pytest",
                "tests/test_p15_split_provider.py", "-q",
                "--junitxml=/tmp/edumind-p15-split-pg-final.xml"],
               cwd=root / "backend", env=env, check=True, timeout=180)
```

## 尚未获得的真实执行依据

完整课程 Schema 的真实兼容性、独立输入边界、sol 总输出限制及当前账号分组费率仍未证明。原两次小合成通过不能替代这些证据。250 次/本地 USD20 保持设计提案，既不是供应商硬限，也不是本轮付费许可。D 未解除前，真实执行入口固定拒绝；后续须先取得证据，再准备准确包与预算单独授权。T039–T042 不推进。

[原设计冻结包](../phase-1.5-split-provider-design-r01/README.md)和历史 DeepSeek 314 项源码冻结保持原字节；新代码放在 scripts/isolated_diagnostics，避免污染历史 acceptance_support 动态冻结范围。此交接仅为 T038 的局部进展，不登记 Task-Completed。
