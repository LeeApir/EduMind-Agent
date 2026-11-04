# T108 r02：规划接口边界修复与新执行准备

2026-11-04。仅零调用准备，待评估；**没有新的真实规划或课程，也没有新真实调用授权**。T108 最终验收仍是实际应用内未经助手补写的新完整课程。head-goal-r01 已停止，1次HTTP400/0规划/0课程，未用2次失效；[旧失败与原件交接](../phase-1.5-head-goal-live-r01/RESULTS.md)保持。旧预算、窗口、批准和 C2 不继承。

本次只有规划接口、准确请求摘要和对应入库版本标记变化。共享示例引擎、教学材料/Schema、响应适配、加密原件保存、私有课程/版本/反馈和 Vue 组件复用 T108 已有接线，无教学补写或通用编译器。最小代码范围见下表，定向结果见 [CHECKS.md](CHECKS.md)，集中契约差异见 [ADR0052 r02 补充](../../ADR/0052-planning-wire-r02.md)。

## 三个真实请求构造

| 阶段 | 实际函数与协议 | 本次差异 |
| --- | --- | --- |
| 规划 | `scripts/head_course_goal.py:planning_body` → `head_course_planning_wire.build_request`；Responses `text.format.type=json_schema`、strict=true；线格式 v2 | 不再直接发送原业务 Schema；新 Prompt 明确空数组/空串规则，无相互矛盾的 null 要求 |
| 教学首稿 | `head_course_materials.content_payload/body(payload)`；同一 Responses 格式，`head-goal-course-v1` | 无改动；显式类型对象/数组/基础字段，无条件联合或引用 |
| 唯一允许修复 | `head_course_materials.body(payload,parent,issues)`；同一教学 Schema，修复 Prompt | 无改动；精确父候选和独立允许意见，返回完整正文，不是补丁 |

[planning-request.template.json](planning-request.template.json) **由实际 planning_body 构造**，包括完整实际 Prompt、准确目标/自述先备/支持域、空画像和新线 Schema；仅 course/operation/request UUID 为显式占位符。它不是伪造模型规划。实际发送前须用真实应用保存的身份/目标重新构造、原样保存请求及 SHA。教学与修复的真实规划/父稿尚不存在，不伪造其最终请求字节；构造函数、系统词、Schema、新示例材料和协议清单均已冻结。

模型配置三个阶段均为：`https://api.deepseek.com/responses`，`deepseek-flash`，reasoning none，temperature 0.2，max_output_tokens 8000，stream=false，store=false，无工具/重试/回退。实际回包 model 严格核对，别名权重不保证不可变。响应继续只接受缺省或 final_answer 消息 phase，其他阶段/未知字段继续拒绝。新线格式尚未真实验证，不把 T106 教学结构的成功外推为本规划成功。

## 新旧格式映射

| 新远端线格式 v2 | 原本地业务 v1 | 拒绝条件 |
| --- | --- | --- |
| protocol_version | 显式转换版本，留在 mapping 审计 | 非准确 v2 或未知字段 |
| needs_clarification=false；plans=[一个完整对象] | plan=该原对象 | 0/多计划、不合法正常分支 |
| needs_clarification=true；plans=[] | plan=null | 带非空计划、缺问题/原因/准确来源 |
| 正常 reason="" | reason=null | 澄清空原因、正常非空原因 |
| planner_suggestion 的两个来源字段均为 "" | 两字段为 null | 有任何非空证据时拒绝，不能默默删掉 |
| user_requirement 引用、目标/术语/约定/场景/问题等其他字段 | 原样映射 | 原完整 Schema/来源子串/覆盖/先序依赖/范围检查失败 |

线 Schema 在 [planning-schema.json](planning-schema.json)，本地完整 Schema 原样在 [planning-local-schema.json](planning-local-schema.json)。本地 SCHEMA/validate_response 未弱化；规则继续包括目标集合覆盖、真实来源白名单和准确引文、唯一ID/术语/场景、前序依赖、示例ID与四种形式。真正是否覆盖两项学习目标、是否应澄清仍需独立语义检查，不能靠ID存在自证。

代码：`backend/app/agents/head_course_planning_wire.py/.schema.json` 明确手写有限格式和严格转换；原 CLI 选择此构造并保存/复核 `plan.mapping.json`；`free_course_planning.persist_outcome` 仅对 head_support 分支绑定新请求摘要和 prompt_version，普通规划不变。离线 fixture/test 只迁移格式，绝不被真实入口当后备规划。教学/课程/答案/API/数据库 Schema 不变。

## 新真实批次提案（当前不执行）

| 约束 | 准确值 |
| --- | --- |
| 目标 | 我已了解 C 指针、struct、NULL 和函数返回值，希望通过头插示例，理解新节点如何连接旧链表，以及为什么调用者需要接收函数返回值。 |
| 示例 | 真实规划仅从 head-new-A/B 选择一个，沿用准确新材料；不得使用 C01/C02、手写大纲或离线夹具填充 |
| 调用上限 | 最多3 HTTP：规划1、正文1、有条件普通措辞修复1；非3次任意试错，无探测/echo/模型审核 |
| 窗口 | 执行前新登记 starts_epoch/expires=starts+600；同时受实际新应用操作600秒期限约束，取较早截止；不延窗/续跑 |
| 大小/预约 | 每请求≤131072字节、响应采集≤2097152字节；输入预约139264/次、合计417792，输出请求8000/次合计24000；预约不是上游 token/金额硬界 |
| I/O和金额 | 单项I/O timeout90秒，DNS同步，非硬总时钟；实际金额无可验证硬上限，C2须本批另批 |
| 外发 | 本准确公开目标/自述先备、本次课程/操作/请求UUID、真实规划、新程序材料/参考答案、准确父稿/定位意见；无历史画像/H/旧私有候选/真实作答/助手修订正文 |
| 审核 | 先机械转换/完整本地校验，再独立评估助手核对真实规划；通过才正文。首稿/修复稿完整核对目标、事实、题目不泄题、作用域/高亮/判空/生命周期/答案及页面版本 |
| 允许修复 | 至多一次独立认定的 minor difficulty/misconception 普通教学措辞；精确path/quote/父摘要。不得修规划、协议、Schema、事实、答案、安全或unknown |
| 停止 | 简化规划被拒立即保存准确错误和STOP，交用户决定Provider路线；其他拒绝/越域/澄清/不通过/原件不全/未知/超限/到期也停，余量失效。无自动字段补丁、探测、重试、换路由 |

沿用 ADR0052 A—D 的程序/模型所有权、支持域和本机前台局限，变更仅见补充。当前拟议批次 `head-goal-r02`，须新私有目录，例如 `/Users/apir/.local/share/edumind/head-goal-r02/`，不能使用旧目录/旧操作。批准应绑定本提交/manifest 并明确 `planning_wire_version=head-goal-planning-wire-v2`、`version=head-goal-course-v1`、`explicit_user_authorization=true`、`accept_ADR0052_R02_and_batch_C2=true`。旧批准字段即使有余时也拒绝。新批准登记只能在真实用户授权后写入，不预填为已授权。

## 获准后的课程执行路线

1. 确认本机隐藏输入可用后才登记新600秒窗口；从现有实际目标页 [http://127.0.0.1:5198](http://127.0.0.1:5198) 提交准确目标，取得当前私有owner/course/operation，新课程绝不覆盖旧失败记录。必要时按既有开发启动命令重启到新提交；本轮没有启动真实生成。
2. 用原 CLI `--prepare --owner … --course … --operation … --vault <新目录>` 读实际应用快照和生成新规划请求。最小环境仅需PATH/PYTHONPATH/专用本机测试数据库，禁止读取项目.env或传入Provider环境变量。
3. 同 CLI `--send plan --vault … --approval …`，Key只在 `Current DeepSeek API key (not saved):` 隐藏提示下输入，不能在shell提示符或聊天输入。完整原body先加密/fsync；`plan.output.json` 保留原线JSON，`plan.mapping.json` 保留版本/原与转换摘要/本地值，再存规划和outline。拒绝即停，不在本批修协议。
4. 独立评估真实规划通过写准确 plan-review，才 `--send generate`；模型完整正文无助手兜底。首稿独立通过或唯一普通措辞修复后完整重评通过，才 `--publish` 入现有私有manifest v2；首稿、失败和父修复链全保留。
5. 在同一实际私有身份完成阅读、代码/状态/高亮与逐帧演示、暂停/前后步/重置、四题错误/正确反馈及刷新后版本一致，交独立教学评估后停止。Mock、回显、接口接受、仅规划通过均不是最终交付。

执行命令统一 `backend/.venv/bin/python -I scripts/head_course_goal.py`，不另建发送器。原收集器/消息适配/来源绑定/现有组件复用；本次已核对请求实际构造，未调用Provider。静态复现：`backend/.venv/bin/python scripts/prepare_head_course_goal_wire_package.py --check` 与 CLI `--inspect`。

STOP/Ctrl-C/页面取消依旧尽力：可能检查后暂停迟发、在途继续计费；页面只围栏入库，不能给终端发信号。保留ACTIVE/STOP，不清锁复用。原件本机0700/0600加密保存，没有独立保管/抗回滚保障；partial/unknown不能当完整。T102 blocked未解除；不扩主题、T038或生产开放。

本轮交付接线修复与准确包供评估，**评估后再申请新批次授权**。真实新课程未完成前T108不done，不创建Task-Completed。
