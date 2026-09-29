# MVP-0.3-T018 单 Tutor 按需角色编排验收与交接

在 T017 的 `enabled_roles` 与 `generation_id` 门禁底座上，实现 P0 的单 Tutor 课堂编排：一次课堂动作只由**一个 Tutor 编排**，专注模式仅导师发言，互动模式按需让基础/进阶同学发言，且不要求所有角色发言、不重复改写同一内容。本任务为纯 agent 层交付（无 API、无迁移、无 Provider 实调）。

## 实现

- [classroom_roles.py](../../backend/app/agents/classroom_roles.py)：**版本化固定角色画像**（`classroom-roles-v1`）与确定性发言资格选择。启智导师/基础同学/进阶同学三张固定 `RolePersona`（name/responsibility/speaking_style/trigger）只决定表达方式，不改知识事实；`select_speaker_roles` 专注模式恒返回 `(tutor)`，互动模式返回 `tutor +` 按产品序去重的基础/进阶同学，未知角色/未知模式拒绝，同学角色仅为候选、不强制全部发言。
- [classroom_turn_schema.py](../../backend/app/agents/classroom_turn_schema.py)：**turn 输出 schema**（`classroom-turn-v1`）与确定性冗余守卫。`validate_classroom_turn` 强制：恰好一个 tutor 主发言、每角色至多一次、`text` 不得跨角色逐字重复、所有发言者必须在 `eligible_roles` 内（专注模式因此不可能产出同学发言）。同知识点“多角色重复改写同一内容”在结构层被排除。
- [classroom_context.py](../../backend/app/agents/classroom_context.py)：**上下文最小化**（`classroom-turn-context-v1`）。仅发送当前目标、当前节点事实、前置节点、**已审核资源**、必要画像信号与紧凑路径上下文；排除原始 evidence（source/confidence/observed_at）、未审核资源、无关画像字段与消息历史。
- [tutor_agent.py](../../backend/app/agents/tutor_agent.py)：**TutorAgent** 单次结构化生成一个课堂回合；模式感知的 system 指令只在互动模式注入同学发言规则。`orchestrate(mode, enabled_roles, context)` 一次 Provider 调用 + 校验，返回 `TurnOrchestration`（`turn` 或可恢复 `failure`）；Provider 失败/非法输出返回带 `ProviderErrorCode` 的可恢复状态，**不触碰任何已审核资源**。

## 验证

- [test_classroom_roles.py](../../backend/tests/test_classroom_roles.py)（5）：画像固定/版本化；专注恒仅导师；互动按产品序去重、输入序无关、空角色仅导师；`tutor`/未知角色不入同学集合；未知模式与未知角色抛 `ValueError`。
- [test_classroom_context.py](../../backend/tests/test_classroom_context.py)（7）：当前事实/前置/目标/已审核资源齐全且上下文不可变；只发送相关已知字段且**不含** evidence/私隐值（`private`/`manual_correction`/`confidence`/`observed_at` 等逐项排除）；未知或无证据字段不发送；路径只保留 current/prereq/next/reasons；缺节点或缺目标抛 `ValueError`。
- [test_tutor_agent.py](../../backend/tests/test_tutor_agent.py)（15）：专注一次调用仅 tutor；互动允许同学且 system 指令列出资格画像；互动回合可仅 tutor（不强求同学）；专注拒绝同学发言/重复角色/跨角色重复 text/缺 tutor/非法形状；Provider `TEMPORARILY_UNAVAILABLE`/`RATE_LIMITED` 返回可恢复失败；非法模型输出映射为 `INVALID_OUTPUT` 失败。
- `ruff check app tests` 与 strict `mypy app`（81 源文件）通过；与既有 agent 层测试合计 79 项通过，无 Provider 实调、无数据库依赖。

## 下一任务

T019「分级审核的课堂流式发言」在本任务上把 `build_classroom_context` + `TutorAgent.orchestrate` 接入 POST SSE：普通对话走版本化轻量规则、高风险内容升级审核、持久化会话记录/游标并支持幂等恢复与断线/取消/模式切换竞态；T020 再接通真实 API/SSE 的前端界面，不得只做静态 UI。
