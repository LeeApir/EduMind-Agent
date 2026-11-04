# T108 r02 定向检查与交接

2026-11-04；真实 Provider 新请求 **0**。这些是接口边界与接线检查，不是新课程生成或教学通过。

| 实际检查 | 结果与范围 |
| --- | --- |
| `PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q backend/tests/test_head_course_planning_wire.py` | 21 passed。正常无损转换/空标记、澄清分支、错误来源与引文/覆盖/依赖/示例范围/未知版本字段拒绝；三构造的实际 Schema/Prompt、旧批准拒绝；新简化规划模拟400加密原件与STOP、禁止后续发送。没有网络或模型成功。 |
| 专用本机PG下 `tests/test_head_course_goal.py::test_goal_plan_private_course_and_feedback[head-new-A]` 及 `::test_exact_entry_mock_transport_and_raw_failures` | 3 passed，1条既有Starlette弃用提示。原save_plan实际PG保存本地v1格式/新prompt_version/真实新request_digest；既有私有课程与反馈链通过。真实发送入口用MockTransport捕获规划/正文/修复三个请求的Schema，规划/正文成功，未知phase/非法JSON拒绝并保留原件。夹具明确非真实模型课程。 |
| `backend/.venv/bin/mypy --follow-imports=silent backend/app/agents/head_course_planning_wire.py backend/app/services/free_course_planning.py` | Success: no issues found in 2 source files。 |
| Ruff检查两后端源、新旧限定CLI/fixture/新包生成器与两定向测试文件 | All checks passed。 |
| `python3 scripts/check_catalog_workflow.py`、`git diff --check` | 通过，活动账本依赖有效。 |
| `backend/.venv/bin/python scripts/prepare_head_course_goal_wire_package.py --check`、`backend/.venv/bin/python -I scripts/head_course_goal.py --inspect` | 新包逐字节重建及实际入口摘要核对；仅静态检查，不发请求。 |
| 对照 `221ae7a` 的旧准备包/停止批次/ADR0052原件与批准、T104/T106/T107目录，以及其他107项Task、process前缀 | 原文件未改；T102仍blocked；日志只追加。旧来源代码按旧提交复现，不能拿新入口去重解释旧批次。 |

PG测试精确复现（只读专用测试库环境，不读取项目.env、Provider Key或终端记录）：

```python
import json, subprocess
from pathlib import Path
root = Path.cwd()
env = json.loads(Path('/tmp/edumind-t108/env.json').read_text())
subprocess.run([
    str(root / 'backend/.venv/bin/python'), '-m', 'pytest', '-q', '--tb=short',
    'tests/test_head_course_goal.py::test_goal_plan_private_course_and_feedback[head-new-A]',
    'tests/test_head_course_goal.py::test_exact_entry_mock_transport_and_raw_failures',
], cwd=root / 'backend', env=env, check=True)
```

首次在工具沙箱内运行这3项因本机15437连接权限被拒，不能计通过；使用工具授权的本机PG访问权限后，同一组3项通过。没有修改断言或把失败当skip。只使用原专用 `edumind_catalog_p15_t108_dev`，没有触及旧真实失败课程、STOP/ACTIVE或任何Provider原件。

没有改前端、教学Schema、引擎、迁移和产品反馈，因此没有重跑旧59规划/18回放/全量前端/迁移/浏览器套件。已有 T108 接线证据仅复用其工程结论；下一真实授权后必须在真实新课程上重新做完整学习流程和独立教学评估，不能沿用夹具教学结论。

交接：本次解除规划接口直接外发内部复杂Schema的明确前置。新增线格式、严格转换和原件映射审计，未生成教学内容。代码/协议与准确包交评估，评估后才申请新的真实授权。简化规划若仍被拒，准确记录并立即停，Provider路线由用户决定。本任务不done，不记Task-Completed。
