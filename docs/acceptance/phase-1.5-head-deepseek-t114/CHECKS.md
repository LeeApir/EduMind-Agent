# T114 离线验证记录

本轮真实 Provider 调用为 0，未创建实际发送授权或启动真实批次。独立教学评估及实际浏览器学习验收在新课程生成后进行。

| 核验 | 实际结果 |
| --- | --- |
| 封存原件重放 | T113 去敏观测逐字节一致。两份 DeepSeek 官方封存样本通过新增回执规则。AIAPI 原失败、STOP 及 T112 限定导入绑定仍可重放。 |
| 新接口契约 | 17 项通过。覆盖模型、存储、温度、上限、工具、附加指令、推理用量、未知字段、回显 Schema 变化及修订上限。 |
| 隔离 PostgreSQL 与真实应用接口 | 在 `edumind_catalog_p15_t108_t114` 迁移至 head 后，8 项通过。六个新批模拟传输用例覆盖直接准入、局部修订、重复题目成员恢复、协议拒绝、剩余 89 秒拦截、过期回执封存。应用操作与前台窗口完全一致。通过路径检查私有 v2、来源标记、13 帧和服务端四题反馈及再读。另两项覆盖固定首稿材料和修订范围。 |
| 包与应用静态核对 | 冻结文件重算、入口检查、Ruff、前端类型检查及定向 ESLint、工作流和 Git 差异检查通过。 |

```sh
backend/.venv/bin/python scripts/run_head_course_goal_dev.py --profile direct --prepare
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q backend/tests/test_head_course_deepseek_wire.py
backend/.venv/bin/python - <<'PY'
import json, subprocess, sys
with open("/tmp/edumind-t114/env.json") as f:
    env = json.load(f)
sys.exit(subprocess.run([
    sys.executable, "-m", "pytest", "-q", "backend/tests/test_head_course_fixed.py",
    "-k", "deepseek or exact_first_request or scoped_merge",
], env=env).returncode)
PY
PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.check_head_course_provider_review
PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.prepare_head_course_deepseek --check
backend/.venv/bin/python -I scripts/head_course_goal.py --profile direct --inspect
pnpm -C web typecheck
pnpm -C web exec eslint src/components/CourseWorkspace.vue
python3 scripts/check_catalog_workflow.py
git diff --check
```

命令里的开发环境文件含本机测试库连接资料，仅供本机进程读取。证据文件使用离线夹具及封存回执。
