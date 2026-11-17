# T107 头插课程开发主链接入：待审查的必要契约差异

当前交付是接线前的准确契约与可重建映射，**尚未交付应用访问入口或实际应用学习流程**。T107 未完成；没有 Provider 调用、数据库写入或产品运行代码变更。T106 原件及已有课程入口不变。

## 固定输入与所有权

| 输入 | 准确候选 digest | 使用版本 |
| --- | --- | --- |
| [C01 原件](../phase-1.5-limited-c-live-r01/C01-generate.candidate.json) | e80a6cd201bb12add78fe74b973df432bdef544306b33c8ec63f312c3d4856f1 | 首版，13 帧 |
| [C02 原件](../phase-1.5-limited-c-live-r01/C02-repair.candidate.json) | 94b98e3411cdffdce46a77387aac92d3333731e5bae340e2e886cad82596dea0 | 唯一模型修复版，10 帧；保留父稿 11733f29cba774f7273429bc20326f40eae9b38e02f727f9ebf6435df9573a51 |

模型拥有 prerequisites、paragraphs.text、每步 title/note、四题 stem/explanation、failure_scope、lifecycle、learning_summary；映射逐字符串相等，不拼写或补写教学正文。程序拥有代码、状态、frame/fact 对应、行号、局部作用域标识、参考答案、控件和来源标签。来源审计由 T106 delivery-manifest 文件 SHA、候选语义 digest、父稿 digest 三层校验；不读取私有 raw.key 或 API Key。

`*.private.proposed.json` 是服务端保存方案审查附件，**不能作为前端资源导入**；包含原件准确 UTF-8、私有参考答案和解析、所有源字段 JSON pointer 映射及 fact 绑定。`*.public.proposed.json` 仅含公开课程字段与安全来源元数据，无 answer_key/solution/原件全文；两份文件中的 UUID 是确定性的提案示例值，真实保存由现有仓储分配 owner 绑定身份。

## 核对出的差异

| 项目 | 现有产品协议/代码证据 | 直接降格会造成的问题 | 必要变更 |
| --- | --- | --- | --- |
| 逐步讲解 | VisualStep 仅 caption/elements/highlight_ids；CoursePresentation 的动作游标与手动状态游标独立 | 每帧 title/note 无受约束对应位置；状态手动前进时原代码高亮可能不变 | ADR0051 B：新类型承载完整帧，一游标控制所有展示，重置回首帧 |
| 指针作用域 | VisualElement 仅 id/label/next_id；调用者/函数局部无结构字段 | 将返回后遗留的 local_head/p 当成活动变量 | B：保留完整 state，显式 active/inactive；inactive 时主视图不显示活动局部值，准确状态可查看历史快照 |
| 未初始化字段 | next_id 只接受 null 或本步已存在节点 ID，准入检查目标必须存在 | t0.next=indeterminate 不能改写为 NULL，也不能造出一个叫 indeterminate 的实结点 | B：新类型保留原状态中的 indeterminate，准确展示未知；旧类型规则不放宽 |
| 代码行高亮 | Action 只有 highlight_block/show_step/pause；CourseWorkspace 整个 code.source 渲染为一段 | 第 4 行分配、第 5 行判空和第 6/7/8 行无法准确同步 | B：每帧同版本 code_anchor+line；成功判空复用分配后 state，但 line=5，不能假装新增引擎执行步骤 |
| 数组答案 | Question 只接受 short_text；Answers.provisional 通过 `_canonical_answer` 文本比较 | `[2,1,9]` 与 `[2, 1, 9]` 或换行数组 JSON 等价却被判错；C02 `[5]` 与换行格式同样复现 | C：类型化 JSON 整数数组/整数，原作答字符串与旧评分记录保留 |
| 原稿/调用来源 | FreeSceneGenerationResult CHECK sent_attempts=1；展示通过 generation→validation→presentation→ready 读取 | 直接塞入旧模型表会虚增 1 次真实生成；只写 scene 表也不能通过 read_ready_scene | A：显式 replay origin+0 attempts 的迁移/约束，仍走现有准入与 ready 记录，不造模型响应 |
| 版本与答案私有 | scene API 通过 public_exercise 删除答案；按课程/场景/题组准确身份读取反馈 | 将 T106 HTML 或完整候选作为前端 import 会暴露参考答案，且无法刷新读取私有记录 | A/C/D：私有原件入库、公共来源投影；现有 Answers 与 CourseExercise 反馈路径保持 |
| 开发边界 | 默认 catalog_only 禁新草稿提交；现有 CourseExercise 也据此只读 | 为样例直接修改生产默认会扩大开放范围 | D：独立开发 DB/本机端口、禁 Provider/出站的实例；不改变生产配置 |

来源代码：`backend/app/agents/free_scene_generation.schema.json`、`backend/app/contracts/free_course.openapi.json`、`backend/app/services/free_scene_validation.py`、`free_scene_actions.py`、`free_scene_availability.py`、`free_course_answers.py`、`quiz_scoring.py`、`backend/app/models/free_scene_generation.py`、`web/src/components/CoursePresentation.vue`、`CourseWorkspace.vue`、`CourseExercise.vue`。准确摘要在 manifest。

## 可复核附件与实际检查

- [ADR0051 A—D](../../ADR/0051-head-course-development-replay.md)：集中批准范围，涵盖最小持久化迁移、教学状态、输入与开发边界。
- [提案 Schema](proposed-scene.schema.json)：旧公共定义保持，仅新增明确类型/来源及新输入 enum；正常模型生成 Schema 不改。
- [C01 公共投影](C01.public.proposed.json) / [私有保存映射](C01.private.proposed.json)。
- [C02 公共投影](C02.public.proposed.json) / [私有保存映射](C02.private.proposed.json)。
- [检查结果](mapping-check.json)：原文映射 C01 45 处、C02 37 处；完整13/10帧逐值派生；旧契约拒绝、新提案 Schema 接受；每例行号/作用域/未知 next/题外补字/父稿/原件字节六种篡改均拒绝。完整原件保留，也保留模型字段内所有 fact_ids。

实际执行：

```sh
backend/.venv/bin/python docs/acceptance/phase-1.5-head-replay-t107/prepare_mapping.py
backend/.venv/bin/python docs/acceptance/phase-1.5-head-replay-t107/prepare_mapping.py --check
backend/.venv/bin/ruff check docs/acceptance/phase-1.5-head-replay-t107/prepare_mapping.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

系统 python3 无 jsonschema，首次离线导入失败；项目 venv 中需显式加入仓库根与 backend 路径，已由脚本自行设置。两次失败均在任何输出/DB/网络操作前，不是课程或 Provider 失败。最终检查以项目 venv 命令为准。

## 批准后仍须完成

1. 按 A—D 补充运行契约、迁移与回归，固定来源导入器复用现有仓储/准入/展示/ready 原子链，不增加导入 HTTP、独立播放器或调度框架。
2. 启动实际本机开发 API/Vue 与专用 PG，用实际浏览器身份导入两课，经现有学习历史/课程页打开；不得以 API route mock 或独立 HTML 充作主链接入。
3. 浏览器逐帧讲解、代码、状态、行高亮、作用域、判空及四题格式/错误/正确反馈；播放/暂停/前后/重置；刷新重读准确数据库版本与反馈，核对 GET 不泄漏答案、跨 owner 与旧版本评分围栏，Provider 0。
4. 提供实际访问 URL/启动重开方式及检查记录后交评估。当前没有伪造 URL、PG 或浏览器通过记录；评估未执行，不以 T106 原教学评估代替新主链验收。

项目 AGENTS.md 要求“涉及尚未批准的重大 API/数据/安全决策时，及时标记 blocked 并向用户求助”。本次 B/C 改变已批准教学投影和评分，A 改变持久审计来源，因此需要准确批准后再继续依赖实现。T107 保留未完成；T102 blocked、T106 原件及三处用户无关改动不变。
