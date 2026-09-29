# MVP-0.3-T030 核心集成验收

## 结论与边界

在独立数据库 `edumind_t030_stage_20260929`（Alembic head）、真实 FastAPI、Vite 和 Chromium 中，`web/tests/e2e/real_stage_flow.py` 完成同一次会话的已审核讲解与练习（2/2）→专注切互动→启用角色并发言→数组与链表多视角及显式反馈→返回原课堂且练习回执保留→切回专注→真实已审核 Manim 模板缓存 MP4 播放（36 秒、无媒体错误）→Markdown/MP4/SRT 下载。三种下载均有非空字节，下载期间没有新增 POST 请求。课堂发言、多视角生成及审核由确定性 mock Provider 驱动；这是前后端、持久化和真实模板媒体的集成证据，不是付费真实 Provider 质量或新渲染性能证据。

首次全旅程暴露辩论组件在切换模式、角色和发言后沿用旧 `revision`，开始辩论返回 409。组件现于创建幂等请求前读取最新课堂快照；新增 `debatePanel.spec.ts` 回归断言发送最新 revision。修复后完整旅程通过。

## 实际验证

| 检查 | 结果 | 边界 |
|---|---|---|
| `uv run python ../web/tests/e2e/real_stage_flow.py`（`backend/`，隔离库） | 通过，输出 `Real MVP 0.3 full browser journey passed` | 真实 API/PG/浏览器/已缓存真实模板媒体；模型 mock |
| `uv run pytest tests -q`（`backend/`，隔离库） | 649 passed、5 skipped、9 warnings | 数据库与 API 全量回归；5 项需显式 Docker 开关，不计通过 |
| `pnpm test`（`web/`） | 19 个文件、122 passed | 包含辩论最新版本回归 |
| `pnpm e2e`（`web/`） | 通过 | 路由 mock 浏览器：练习、移动端、Provider 故障、审核拒绝、SSE 恢复、课堂控制与场景版本；另含下载键盘操作 |
| `pnpm build`（`web/`） | 通过 | Vue 类型检查与 Vite 构建 |
| `pnpm exec eslint src tests`（`web/`） | 0 errors、67 个既有格式 warnings | 无本任务新增 lint 错误 |
| `uv run ruff check app tests ../web/tests/e2e/real_stage_backend.py ../web/tests/e2e/real_stage_flow.py`；`uv run mypy app`（`backend/`） | 均通过；Mypy 检查 95 个源文件 | 静态检查 |

以上 PostgreSQL 命令均使用 `EDUMIND_TEST_DATABASE_URL` 和 `EDUMIND_DATABASE_URL` 指向新建隔离库；凭据仅在进程环境中传递，未写入仓库。未设置数据库时的旧结果为 505 passed、149 skipped，不作为本次数据库通过证据。5 个 Docker 跳过项为真实渲染、容器停止与独立 Worker 进程；由 T031 重启恢复与 T032 新渲染性能的专门隔离验收覆盖，本任务不把跳过记为成功。

## 异常与旧链路覆盖

| 风险 | 已执行回归 |
|---|---|
| 动画排队、取消与失败 | `test_animation_job_api.py` 的缓存/幂等、取消与发布竞态、失败重试；`test_animation_worker.py` 的并发领取、租约过期、旧尝试不可发布、坏媒体和渲染失败后学习资源保留 |
| 审核拒绝、Provider 故障 | `test_classroom_speech_api.py` 的高风险拒绝撤回与生成错误；`test_debate_api.py` 的审核拒绝/不可用与生成失败；`test_scene_reexplanation_api.py` 的审核拒绝、不可用、Provider 失败；`test_learning_sessions.py` 的正式资源拒绝与 Provider 失败；浏览器路由 mock 复验用户可恢复界面 |
| SSE 中断与版本恢复 | `test_debate_api.py` 断流释放操作，`test_classroom_speech_api.py` 模式切换使迟到提交失效，`test_scene_reexplanation_api.py` 竞争发布与旧版本拒绝；路由 mock 浏览器覆盖 SSE 恢复/场景版本，真实全旅程覆盖辩论前刷新 revision |
| 普通学习与 MVP 0.2 回归 | 真实全旅程在动画前完成测验并在辩论返回后保留 2/2 回执；全量数据库测试包含 `test_learning_sessions.py` 的无损 SSE 与幂等防重复生成、`test_quiz_api.py` 服务端评分/回执、`test_profile_api.py` owner/画像版本、`test_paths_api.py` owner/推荐路径及其他学习持久化用例 |

本次没有真实 Provider 调用或费用。T033 将单独验证冻结模型的课堂质量与性能；T032 将验证按需实际渲染和模板可用率。
