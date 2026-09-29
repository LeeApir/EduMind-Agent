# MVP-0.3-T019 分级审核的课堂流式发言验收与交接

在 T018 单 Tutor 编排与 T017 课堂模式/幂等底座上，把 `build_classroom_context` + `TutorAgent.orchestrate` 接入 POST SSE：普通对话走**版本化轻量规则**、高风险内容**升级审核**且未通过绝不发布；流式正文无损分块，只有审核通过的回合才提交为 append-only 消息并推进单调游标，同键幂等重放、断线/取消/切模式竞态下旧输出降级 `superseded`，owner 与凭据边界全程保留。

## 实现

- [classroom_speech_rules.py](../../backend/app/agents/classroom_speech_rules.py)：**版本化确定性轻量规则**（`classroom-speech-rules-v1`）。`classify_student_speech` 识别指令劫持/越权或凭据索取请求，`classify_tutor_turn` 识别生成内容中的危险执行/I/O 原语（eval/exec/os.system/subprocess/socket/requests），`combined_speech_verdict` 任一升级即整回合升级；规则纯函数、同一文本永远到同一裁决，绝不发布任何内容。
- [classroom_speech_review.py](../../backend/app/agents/classroom_speech_review.py)：**高风险升级的有界审核**（`classroom-speech-review-v1`）。一次 `TaskProfile.REVIEW` 结构化调用复用 `review_output_schema`/`validate_review`，`pass` 放行、`revise`/`reject` 收回、Provider 失败或非法 review schema 统一映射 `unavailable`——失败的审核永远不可能冒充通过。
- [classroom_speech.py](../../backend/app/services/classroom_speech.py)：**owner 范围 tiered speech 服务**。`reserve_classroom_speech` 以 `classroom_digest(text+scene_version)` 幂等预留、owner 行锁后重查、`revision` CAS；`commit_classroom_speech` 先校验 `revision`/`generation_id` 仍为当前，否则把旧回合降级 `superseded` 且零消息写入；`classroom_messages`/`classroom_operation_payload` 只重放持久消息与操作状态，临时 token 一律不回放。
- [classroom.py API](../../backend/app/api/classroom.py)：POST `/api/learning-units/{unitId}/classroom/messages` 流式 `_speech_events`（agent_start → 编排 → 分级 → token[role] → review_pass → commit → message_ready → done），GET 消息分页与 GET `/api/classroom-operations/{id}` 操作状态；幂等命中走 `_replay_speech` 只回放持久状态。
- [openapi.yaml](../../docs/api/openapi.yaml)：`x-classroom-stream-events.token.data` 补记 `role: tutor|beginner|advanced`，供 T020 按角色渲染。

## 验证

- [test_classroom_speech_rules.py](../../backend/tests/test_classroom_speech_rules.py)（15）：版本固定；中文/英文指令劫持、系统提示词/执行代码/凭据/破坏性请求升级；危险生成原语升级；`free`/`malloc` 指针代码不误报；合并裁决去重。
- [test_classroom_speech_review.py](../../backend/tests/test_classroom_speech_review.py)（6）：pass 放行、revise/reject 收回、Provider 失败与非法 schema 映射 unavailable，请求固定 prompt/instruction/schema 版本。
- [test_classroom_speech_api.py](../../backend/tests/test_classroom_speech_api.py)（11，隔离 PostgreSQL）：低风险分块无损重组并持久化 student/tutor 消息与游标；高风险升级拒绝/不可用发 `content_retracted` 且零 token 零消息；升级但通过照常发布；编排 Provider 失败 `error`+`done(failed)`；同键幂等重放无 token；409 版本冲突；消息游标分页与越界 409；owner 隔离 404；CSRF/Origin 403；切模式中旧 commit 降级 `superseded`。
- `ruff check app tests` 通过；strict `mypy app`（84 源文件）通过；`test_mvp03_openapi_contract.py` 7 项通过；课堂相关测试合计 **73 项通过**。全量后端 557 通过/48 失败/5 跳过，48 失败均为既有环境非回归（动画/链表模板 CRLF 摘要不匹配、首屏毫秒计时抖动、Docker 镜像缺失），与 T017/T018 记录一致；0 Provider 实调。

## 下一任务

T020「专注与按需角色课堂界面」接入本任务真实 API/SSE：默认导师视图、互动时才按需显示同学角色与当前发言者、可随时关闭互动、接通错误重试与课堂恢复、页面转义模型内容；不得只交付静态组件。
