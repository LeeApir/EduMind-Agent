# MVP-0.3-T026 显式视角偏好验收

## 交付

- 只在学生点击已审核演示结果中的“这个视角有帮助”后提交反馈。服务端按 owner、结果 ID、结果版本和视角记录 `explicit_feedback` 证据，返回证据 ID、画像版本及更新状态；相同幂等键重放返回同一结果，换键重复点击同一视角也不会重复写证据。未发布或其他 owner 的结果不可访问，写入受会话与 CSRF 保护。
- 将有证据的偏好写入版本化画像 `cognitive_style.preference_persona`，保留来源、置信度 `0.9`、观察时间和画像版本。用户可在画像修正接口显式改为性能、工程或学术视角；人工修正优先于后续反馈。无原始画像且无法取得学习目标时仅保留证据并返回 `pending`，同请求重放可完成合并。
- 下一轮 Tutor 只读取已保存且有证据的视角偏好，调整例子和表达顺序，不改变算法事实、复杂度或题目条件；该提示词指令版本提升为 `classroom-turn-instructions-v2`。未知偏好不进入上下文；反馈不直接写掌握度。

## 验证

- 隔离 PostgreSQL `edumind_t024_20260929`：定向画像合并/人工修正/幂等/owner/CSRF/反馈到下一轮 Tutor 请求测试 26 项通过；后端全量 `uv run pytest -q` 645 通过、5 跳过。
- `uv run ruff check app tests` 与 `uv run mypy app` 通过；前端 `pnpm test -- --run` 115 通过，`pnpm build` 和改动文件 ESLint 通过。
- `web/tests/e2e/real_debate_flow.py` 在实际 FastAPI/Vite HTTP、隔离 PostgreSQL 和 mock Provider 上验证发布结果、点击视角、画像读取、刷新与退出。无真实 Provider 调用；`git diff --check` 通过。

## 后续

T027 仍为 `todo`。按用户要求，T026 本地完成提交后暂停，不领取后续任务，也不 push/merge。
