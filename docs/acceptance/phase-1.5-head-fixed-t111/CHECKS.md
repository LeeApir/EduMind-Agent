# T111 零调用定向检查

当前准确 manifest 为 `41d2eeb692834b1eacc15327d2f5f0e75e15e9773d8990e6ce48921268bb6de3`，覆盖 410 项文件。已在已有专用 PostgreSQL 容器内创建独立检查库 `edumind_catalog_p15_t108_t111_check` 并迁移至现有 0050。所有响应均为本地夹具经 MockTransport 进入同一发送函数，课程来源为 `offline_fixture`，真实 Provider 调用 0。

| 实际检查 | 结果 |
| --- | --- |
| `python -m pytest -q backend/tests/test_head_course_fixed.py` | 6 项通过。固定例与独立期望、两种事实证据及历史规划请求重建。实际入口与 PG/API 覆盖首稿直达、审核定位修订、格式恢复和协议拒绝停止 |
| 同次运行 `backend/tests/test_head_course_teaching_evidence.py` 及 `backend/tests/test_head_course_reuse.py::test_actual_entry_and_private_application[direct]` | 合计 15 项通过，0 skip。复用证据与旧入口直达回归通过 |
| `pnpm --dir web exec vue-tsc --noEmit`、`pnpm --dir web exec vitest run tests/course-visualization.spec.ts`、`pnpm --dir web exec eslint src/components/CourseWorkspace.vue` | 类型、9 项播放器组件测试与变更文件 ESLint 通过 |
| 变更 Python Ruff、三个类型化规划与材料文件 mypy、`python3 scripts/check_catalog_workflow.py`、`git diff --check` | 通过 |
| `backend/.venv/bin/python scripts/prepare_head_course_fixed.py --check` 与 `backend/.venv/bin/python -I scripts/head_course_goal.py --profile fixed --inspect` | 准确请求可重建，410 项摘要匹配，状态为 prepared_not_authorized |
| 旧 T108/T109/T110 冻结目录、旧 OpenAPI 来源分支与旧规划请求核对 | 历史目录 Git diff 为空，旧 OpenAPI 来源分支完整保留，旧规划请求逐字节重建 |

夹具通过实际目标 API 创建操作，经入口读取输入，保全并回读请求、加密原响应及收据，然后由同一入口准入。直达用 2 条 Mock 请求，修订用 3 条。两者均实际写入 v2，公开场景返回版本来源、13 帧及准确行号、四题且无答案或解析。确认总结和演示替代文本一起装配、范围说明显示最后候选内容。服务端对四题返回课程内反馈，重新 GET 版本相同。格式例外保存 strict-failure，候选标记首次结构未通过。拒绝未知 phase 时原字节仍可解密，STOP 后再次进入被拒。审批门禁拒绝缺少明确许可、错 context 或已绑定窗口变更。

首轮 Ruff 发现导入排序和超长字面量，调整后复验。上述检查是准备阶段的真实存储与页面投影证据。真实模型结果、独立真实教学审核和实际浏览器全流程留给授权后的验收。

独立准备评估由 `/root/head_goal_independent` 完成，针对上述 410 项准确摘要给出 pass。评估方独立执行包重建、CLI inspect、2 项离线测试及 diff 检查，逐帧断言 C 的状态／指针／高亮及四题期望，并重放 T109 首稿与 ADR0054 B 修订请求。确认新画像门禁、首稿证据、修订完整首审、三种允许位置、审批和 STOP。实际 PG 与前端结果来自执行方。评估方新增真实调用为 0。
