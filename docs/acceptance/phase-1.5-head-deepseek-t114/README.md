# T114 固定头插课程 · DeepSeek 官方直连

**执行状态 `prepared_not_authorized`。真实 Provider 调用 0。** 用户已确认 DeepSeek 路线。本包定义下一批的本地入口、证据及真实调用授权边界。[ADR0058](../../ADR/0058-head-fixed-deepseek-direct.md)

[学习目标](goal.txt)使用同一个 `head-new-C` 输入。初始 `[5]`，两次头插 `-2、9`，分配均成功。独立计算的结果是接收两次返回后 `[9,-2,5]`，丢弃两次返回后从调用者入口仍看到 `[5]`，两个新节点不可达。准入后验真实课程正文、13 帧与高亮、播放控制、四题反馈、答案隔离及刷新恢复。[独立期望](independent-reference.json) · [审核政策](../phase-1.5-head-fixed-t111/review-policy.md)

| 冻结材料 | 运行时来源 |
| --- | --- |
| [规划输入](planning-input.template.json)、[规划请求](planning-request.template.json)、[本地规划 Schema](planning-local.schema.json) | 从真实表单绑定三个 UUID。画像为空。规划结构及引用核对后提交独立评估。 |
| [正文请求](teaching-request.template.json) | 使用本批审核通过的真实规划，附同版代码、轨迹、事实、答案和程序证据。 |
| [修订提示](revision-system.txt)、[修订 Schema 示例](revision-schema.template.json) | 仅在审核提出合规阻断时，按父稿与意见计算准确目标。 |
| [配置](candidate-config.json)、[授权模板](approval.template.json)、[manifest](manifest.json) | 授权模板为关闭状态，实际批准记录须绑定准确 manifest、context 及应用窗口。 |

## 获准确授权后执行

1. 确认实际提交及 manifest SHA-256、ADR0058、三次请求上限、30 分钟窗口、C2 费用和停止例外。启动专用开发应用。

   ```sh
   backend/.venv/bin/python scripts/run_head_course_goal_dev.py --profile direct --prepare --start
   backend/.venv/bin/python -I scripts/head_course_goal.py --profile direct --inspect
   ```

2. 评估者与终端就绪后，以全新访客从 [开发应用](http://127.0.0.1:5204/) 提交准确目标。应用操作创建即开始 30 分钟窗口。记录实际访客、课程与操作 UUID。新批 vault 的绝对路径为 `$HOME/.local/share/edumind/head-fixed-deepseek-r01`，权限 0700。准备独立 Fernet 本地加密键 `raw.key`，权限 0600。使用下列命令从专用开发环境启动前台入口。

   ```sh
   vault="$HOME/.local/share/edumind/head-fixed-deepseek-r01"
   mkdir -m 700 "$vault"
   backend/.venv/bin/python -c 'from cryptography.fernet import Fernet; from pathlib import Path; import os, sys; p = Path(sys.argv[1]) / "raw.key"; f = os.fdopen(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"); f.write(Fernet.generate_key()); f.close()' "$vault"
   run_direct() {
     backend/.venv/bin/python -I -c 'import json, os, sys; env = json.load(open("/tmp/edumind-t114/env.json")); os.execve(sys.executable, [sys.executable, "-I", "scripts/head_course_goal.py", "--profile", "direct", *sys.argv[1:]], env)' "$@"
   }
   run_direct --prepare --vault "$vault" --owner "$owner" --course "$course" --operation "$operation"
   ```

3. 核对 `context.json` 和 `plan.prepared-request.json`。在本机私有批准 JSON 中填入 manifest SHA-256、context 原字节 SHA-256 和 context 中的准确 `execution_window`，其余字段按授权模板。两个门禁布尔值只依据用户的真实执行批准设为 true。每次在单前台终端运行一条命令，Key 按提示隐藏输入。

   ```sh
   run_direct --send plan --vault "$vault" --approval "$approval"
   run_direct --send generate --vault "$vault" --approval "$approval"
   run_direct --send repair --vault "$vault" --approval "$approval"
   run_direct --publish --vault "$vault" --approval "$approval"
   ```

4. 规划结构及独立语义通过才发正文。正文直接通过或合法恢复后审核通过，保存独立全文 `final-review.json` 并准入。仅在合规阻断时保存 `repair-review.json` 并发送一次修订。修订后复评全文并保存最终审核。审阅与准入都计入操作时间，学习验收可在截止后完成。首稿、恢复、修订、应用与教学各自记结果。

## 预算与终态

额度为规划、正文、条件修订各最多一次。三次满预约为输入 417,792 和输出 20,000 token，当前公开峰价估算约 USD 0.14934，真实账单金额未知。发前检查窗口剩余至少 90 秒，过期响应仍封存但不能写入新准入。若传输异常、回执拒绝、绑定错误、预算耗尽或结果未知，保存记录并写 STOP。审核阻断时保存意见，再独占创建 STOP。成功准入也写 STOP。ACTIVE 遗留视为未知终态。前台 Ctrl-C 和 STOP 依 ADR0058 的 C2 尽力语义执行。[DeepSeek 官方定价](https://api-docs.deepseek.com/quick_start/pricing/)

本机原件索引覆盖请求、回执、收据、原始字节、应用操作窗口、批准、审核、候选及其来源。索引排除加密键。旧 T111 的拒绝和 STOP、T112 的封存正文限定导入均作为独立历史保留。

## 离线核对

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.prepare_head_course_deepseek --check
backend/.venv/bin/python -I scripts/head_course_goal.py --profile direct --inspect
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q backend/tests/test_head_course_deepseek_wire.py
```

隔离 PG 测试以模拟传输走真实 API 和仓储，独立于正式执行和教学评估。定向结果见 [验证记录](CHECKS.md)。
