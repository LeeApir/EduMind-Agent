# T108 r03 定向检查与交接

2026-11-04。**新真实Provider调用0，未生成新规划或课程。** 本次检查只针对规划依据/职责和同版绑定，Mock或夹具不计模型成功。

| 实际检查 | 结果 |
| --- | --- |
| `PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q backend/tests/test_head_course_planning_basis.py backend/tests/test_head_course_planning_wire.py` | **33 passed**。两候选准确函数/作用域/关键行/独立接收忽略结果；实际planning_body携带原依据、正文/修复同版；代码/局部head/结果漂移拒绝；既有wire/local严格来源/引用/澄清及保存停止检查保留。 |
| 专用PG中原测试 `test_goal_plan_private_course_and_feedback[head-new-A]`、`test_exact_entry_mock_transport_and_raw_failures[phase]` 与新 `test_grounded_review_binding_and_planning_version_refuse_drift` | **3 passed**，一条既有Starlette弃用提示。真实PG/API新Prompt/请求摘要/私有草稿与反馈接线；实际发送入口的三个请求在MockTransport处核对依据；评估绑定缺失/错误及规划Prompt漂移拒绝，未修改原规划记录。 |
| `backend/.venv/bin/mypy --follow-imports=silent` 检查basis/materials/wire/generation/free_course_planning五个源文件 | Success: no issues found in 5 source files。 |
| Ruff检查上述源文件、原CLI/fixture、新包生成器及三份相关测试 | All checks passed。 |
| 项目venv逐对象比较两份完整materials与r02原件、Schema字节/内容 | 两候选代码/帧/事实/答案/materials_digest与r02完全相同；wire v2 Schema原字节、本地完整Schema、教学Schema不变。首次误用系统Python因缺jsonschema未完成核对，改项目venv执行通过。 |
| 新包生成器 `--check`、冻结入口 `--inspect` | 实际规划请求、依据及源摘要逐字节重建一致，无Provider调用。 |
| 工作流/diff/链接、旧停止及冻结包/其他Task/process前缀检查 | 通过；T102保持blocked，日志只追加，三处用户无关改动不纳入提交。 |

PG精确运行使用既有专用 `/tmp/edumind-t108/env.json`（仅测试库环境，不输出、不提交、不读项目.env）：

```python
import json, subprocess
from pathlib import Path
root = Path.cwd()
env = json.loads(Path('/tmp/edumind-t108/env.json').read_text())
subprocess.run([
    str(root / 'backend/.venv/bin/python'), '-m', 'pytest', '-q', '--tb=short',
    'tests/test_head_course_goal.py::test_goal_plan_private_course_and_feedback[head-new-A]',
    'tests/test_head_course_goal.py::test_exact_entry_mock_transport_and_raw_failures[phase]',
    'tests/test_head_course_goal.py::test_grounded_review_binding_and_planning_version_refuse_drift',
], cwd=root / 'backend', env=env, check=True)
```

最后一组检查在最终资料字段固定后执行。没有全量规划/回放/前端/迁移/浏览器重跑，没有对真实原件目录或Key/终端进行操作，也没有重启运行实例或提交新应用目标。历史r02复现须使用其当时提交，不能拿新Prompt/依据重新解释旧失败。

交接：本次解除“规划缺少实际实现依据”的明确前置。候选资料只含程序事实，模型规划仍必须真实生成。独立评估应核对准确请求、提取依据及同版传播；未来真实规划可能仍不遵守材料，仍按原严格独立语义规则决定是否停止，不预先承诺通过。最终新课程和实际学习评估尚未完成，T108不得done。本轮到准备评估停止，新真实授权另批。
