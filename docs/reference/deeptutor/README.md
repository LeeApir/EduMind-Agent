# DeepTutor 实现总结与试用评估

整理日期：2026-10-29。面向 EduMind 的架构参考与教学生成方案评估。

## 1. 结论与资料边界

DeepTutor 值得借鉴的是：以聊天为入口，把检索、出题、学习状态和可视化组织成可调用的工具与分阶段能力；通过持续追问提供教学价值，并在部分专门流程中加入结构、来源和状态校验。

本次头插法试用中，完整 C 程序、文字讲解、丢返回值诊断和自环诊断均表现良好。后续生成 HTML 可视化时，代码接口、数据字段和高亮步骤发生漂移。因此，它提供了可用的教学交互参考，但不能作为“跨讲解、代码、演示、题目的一致性已解决”的证据。

本文区分三类材料：

- **源码机制**：阅读下述固定提交得到的实现事实，未等同于部署环境实测通过。
- **试用观察**：2026-10-28 本聊天中用户提供的教材问答，以及评估助手实际读取的 DeepTutor 聊天和 HTML 源码。
- **设计建议**：面向 EduMind 的取舍建议，不自动成为已批准契约或开发任务。

本文不声称完成 DeepTutor 全量代码审计、测试套件运行、模型质量基准或安全验收。2026-10-29 整理期间没有新增 Provider 调用。

## 2. 版本、部署和入口

| 项目 | 核对值 |
|---|---|
| 官方仓库 | [HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor) |
| 本地源码 | `/Users/apir/Code/GITHUB/DeepTutor` |
| 源码标签 | `v1.6.15` |
| 源码提交 | `a31d82624c27d75f4e771d4fcb78dce16470b383` |
| 实际拉取镜像 | `ghcr.io/hkuds/deeptutor:1.6.15` |
| 用户提供的拉取摘要 | `sha256:602d5dfbac7430e364069ac6672642cb0d764e046d189bf596d9ddc6b775c535` |
| 本地 Compose | 外部仓库中的 `docker-compose.local.yml`，本次部署新增文件，非上游默认配置 |
| Web 入口 | `http://127.0.0.1:3782` |
| 数据挂载 | 外部仓库 `./data` → 容器 `/app/data` |
| 对外端口 | 仅绑定本机 `127.0.0.1:3782`；容器内后端使用 8001 |
| 知识库入口 | 学习空间 → 知识中心，路由 `/knowledge-bases` |

镜像摘要来自用户提供的成功拉取输出；本次未独立证明镜像构建内容与源码提交逐字节对应。源码实现结论以固定提交为准，页面表现以既有试用为准。

本地运行设置保存在 `data/user/settings/*.json`；项目根 `.env` 不作为该版本的设置入口。参考文档不包含真实 Key、个人工作空间端点或设置文件副本。[S01][S03][S19]

## 3. 技术结构与职责分配

前端使用 Next.js、React、TypeScript，并提供 Markdown、公式、代码与文件预览；后端使用 Python、FastAPI、Pydantic。CLI 使用 Typer，另有 Python SDK。依赖声明包含范围约束，具体依赖以该提交锁文件和镜像构建为准。[S02][S03]

核心调用链为：

```text
Web / WebSocket、CLI、Python SDK
                ↓
TurnApplicationService：提交、持久化、取消及回放协调
                ↓
TurnEngine → ChatOrchestrator
                ↓
Capability：接管一轮任务，组织多个阶段
                ↓
Tool：执行检索、读资料、推理等具体操作
                ↓
StreamBus → 事件持久化 / 客户端回放 → 最终结果和用量摘要
```

`UnifiedContext` 提供统一上下文；工具挂载由当前能力与上下文条件决定，并非所有工具始终向模型开放。默认会话存储使用 SQLite，可配置 PocketBase；不能据此推断所有业务数据都采用同一种存储。[S01][S04][S05][S06][S07]

### 3.1 工具与能力两层

| 层次 | 职责 | 例子 |
|---|---|---|
| Tool | 完成一个具体操作，由模型或能力流程调用 | RAG、网页检索、读取来源、推理、工作区文件操作 |
| Capability | 组织一轮较复杂的工作，管理阶段与结果 | 聊天、深度解题、出题、研究、可视化、掌握度学习 |

“多 Agent”并不意味着每次请求都固定启动多个独立模型。多个功能复用聊天 Agent 循环，另一些功能使用专门流水线；逻辑职责、阶段数量、实际模型调用数是不同概念。[S01][S08]

### 3.2 主要能力

| 能力 | 实现要点 | 阅读入口 |
|---|---|---|
| `chat` | 工具探索与回答输出 | [S08] |
| `deep_solve` | 聊天循环叠加解题计划、完成步骤与重规划工具 | [S08] |
| `deep_question` | 探索资料 → 题目计划 → 逐题生成、校验和有限修复 | [S09] |
| `deep_research` | 问题改写、拆分、研究与报告 | [S01][S08] |
| `visualize` | 可视化插件、结构化提交和类型相关校验；可路由到 Manim | [S10][S11] |
| `math_animator` | 概念分析、设计、代码生成、重试和渲染结果 | [S01][S08] |
| `mastery_path` | 聊天循环与学习目标、题目、判分、状态更新结合 | [S08][S14][S15] |
| `immersive_reading` | 基于文档或带时间信息的媒体进行阅读辅导 | [S08] |
| `course_study` | 感知课程状态，按需读取资源并移交后续学习活动 | [S16] |

`course_study` 同时要求选中相应模式并绑定合法课程 ID；它先提供有界摘要，详细资源通过工具按需读取，减少每轮加载整个课程。此处的课程协调能力不能直接等同于 EduMind 的完整课程生成与正式审核契约。[S16]

## 4. 知识库如何参与教学

### 4.1 LlamaIndex 路线

```text
教材 → 解析 → 分块 → Embedding → 本地索引
问题 → 同一向量体系的 Embedding → 向量检索 + BM25 → 合并候选
相关片段与来源 → 聊天模型 → 教学回答
```

- 默认检索画像为 `hybrid`，结合语义向量和 BM25 关键词检索。
- 分块使用 `SentenceSplitter`，大小和重叠由设置提供；试用界面显示的初始值是 `512 / 50`，查询返回数为 `5`。这些是起点，未经过本教材的最优参数评测。
- 有可选重排序配置。Embedding 生成检索向量，Rerank 重排候选，聊天模型生成回答，三类职责不可混用。
- BM25 依赖缺失或构建失败时，代码可退回向量检索；配置写着 `hybrid` 不足以证明运行时实际使用混合检索。
- 本地向量存储支持 FAISS 路线，缺失时有其他本地存储回退。实际后端需要运行证据确认。
- 索引在本地不代表模型调用在本地：使用阿里云等远端 Embedding 时，入库片段和查询会进入所配置服务。

源码见 [S12][S13]。知识库相关性检索不能直接保证回答完整，也不能证明代码、题目或动画正确。

### 4.2 引擎选择

| 引擎 | 功能定位 | 本次建议 |
|---|---|---|
| LlamaIndex | 本地向量与混合检索 | 作为教材问答的第一条验证路线 |
| PageIndex Cloud | 托管无向量检索，需独立 API Key | 有外部服务需求时再评估 |
| PageIndex OSS | 本地无分块、无向量的文档索引，使用当前 LLM，接收 PDF | 可另做同教材对照；不使用 Embedding 不等于没有模型成本 |
| GraphRAG | 知识图谱检索，需要额外依赖，索引过程使用较多 LLM 调用 | 尚未实测，不为首次试用额外安装 |
| LightRAG | 图与向量结合，并提供多模态解析路径 | 尚未实测 |
| LightRAG Server / WeKnora | 连接用户已有的外部知识库服务 | 适合已有对应服务的部署 |

上述引擎选项来自用户实际界面和固定版本的管线目录；本次没有逐一做性能、质量或费用比较。[S20]

### 4.3 上传与模型配置的实际经验

- 知识库通用单文件上限为 `200 * 1024 * 1024` 字节；聊天附件默认单文件上限为 `20 * 1024 * 1024` 字节、每条消息合计 25 MiB，聊天限制可配置。两者不能混为一谈。[S17][S18]
- 本次教材原件约 96.66 MB，按 **PDF 文件页序**裁出前 61 页后约 23.33 MB；裁剪结果超过默认聊天单文件限制，但低于知识库限制。
- 聊天附件解析还存在提取文字与嵌入图片数量等限额，不能将“附件已接受”等同于全文无损进入模型。[S18]
- 用户曾把生成模型及 Rerank 模型填入 Embedding 设置，分别遇到 400 和不支持模型的 404。应使用提供商明确支持的 Embedding 模型；本次建议为阿里云 `text-embedding-v4`，以测试接口实际返回维度为准。本文未保存或独立确认最终成功配置。

## 5. 如何控制生成与评分质量

### 5.1 出题：减少单次生成负担，检查结构并有限修复

`QuestionPipeline` 先探索，再生成逐题模板，最后按模板逐题运行生成循环。单题完成输出为严格 JSON，解析、规范化后增量发送题卡；结构异常进入有限修复。最终汇总按题目残留 `issues` 统计成功和失败，不将所有返回题卡一律计为成功。[S09]

这些机制能提高可消费性，但结构校验本身不证明答案正确。默认聊天中临时列出三道题，也不能直接视为执行了 `deep_question` 的专用流程。

### 5.2 教材学习：绑定真实来源

`lesson_evidence.py` 对来源身份、引文与目标绑定进行程序检查；有界准备流程最多选择六页来源。不匹配的引文可被拒绝，资料不足可进入不可用状态。文件开头明确说明，来源核验与模型判断材料是否适合教学是不同层面的保证。[S14]

这属于特定教材学习流程，不能推广成“所有普通聊天引用都由程序验证”。本次普通问答仍出现错误 PDF 页码。

### 5.3 判分：确定性匹配与语义判断结合

`semantic_assessment.py`：

1. 选择题按已存答案标签判定；与已存标准答案或可接受答案精确匹配时，可直接给出结果。
2. 其他情况可请求语义判断，允许 `correct / partial / incorrect / ungraded`。
3. 模型返回的置信度不足 0.8 时，收据转为 `ungraded`，保留需要澄清的状态。
4. 题目契约指纹、来源与答案在服务提交学习结果前再次检查；部分有来源题目还核对题干和答案依据。

模型自报置信度不是经过校准的准确率；精确匹配也只能证明与已存答案一致，答案本身仍需依据。源码中还存在旧式字符串相似度/关键词判分函数，不能仅看到该函数就认定当前所有学习流程都使用它，应跟随服务调用链判断。[S15]

### 5.4 学情记录：保留证据和未知状态

`teaching.py` 将学习偏好和教学观察分开。偏好要求学生明确表达，证据必须来自当前学生消息的原文；教学观察绑定当前目标，策略效果允许 `unknown`。这层检查结构、范围与来源，不直接推断“已经掌握”。[S21]

### 5.5 可视化：有提交协议，跨产物一致性仍需另验

专门 `visualize` 能力通过 `submit_visualization` 交付画布数据，并使用插件声明的结构或专用校验器；工具调用不支持、没有合法输出等情况有明确诊断。Manim 使用另一组阶段。[S10][S11]

本次实际可视化是在聊天中通过工作区工具生成独立 HTML，不能把它的错误直接归因于专门 `visualize` 插件的校验实现，也不能假定该 HTML 已经过同样的审核。

## 6. 实际试用结果

### 6.1 教材问答

用户提交的两轮回答先比较顺序表与链表，再追问空间性能和单链表删除条件。

- 第一轮主要知识正确，写明链表 O(1) 修改的前提，适合初学者阅读；但漏掉相邻的 §2.6.1 空间性能比较。
- 追问后正确补充空间分配、存储密度、前驱结点要求及复制后继数据技巧的限制。
- 页码不可靠：§2.6.1 在书内第 40 页、PDF 第 52 页；插入删除效率段在书内第 41 页、PDF 第 53 页。回答把 PDF 页序错误写成 40 / 41。
- 这些页码由评估助手直接读取用户提供的裁剪 PDF 核对。试用体现了较好的教学解释能力，页码错误影响来源核查，不抹消知识回答的价值。

### 6.2 单链表头插小课

会话标题为“单链表头插法 C11 入门示例”。用户要求不带头结点、从空表依次插入 4、7、9，包含完整 C11 程序、逐步说明和三道暂不公布答案的练习。评估助手实际读取了该会话及生成 HTML 的页面源码。

| 检查项 | 观察结果 | 证据边界 |
|---|---|---|
| 完整程序 | `int push_front(Node **head, int value)`；失败返回 0，调用方释放已有链表后退出 | 严格编译和正常执行通过；未注入 malloc 失败，也未做完整内存分析 |
| 正常轨迹 | 依次输出 `4 → NULL`、`7 → 4 → NULL`、`9 → 7 → 4 → NULL` | 运行结果与文字表格一致 |
| 丢弃返回值 | 正确指出调用者 `head` 保持 NULL、两个新结点泄漏 | 实际阅读回答，未运行泄漏变体 |
| 先改 head 再接 next | 正确指出新结点自环、旧链表入口丢失 | 实际阅读回答 |
| 三道练习 | 覆盖执行结果、连接顺序、错误诊断 | 没有观察到完整逐题作答和批改 |
| 生成工具失败恢复 | `apply_patch` 不存在后，改用 Python 生成 HTML | 会话中可见工具轨迹；不等于内容审核通过 |
| 可视化最终链表 | HTML 状态数组最终为 `[9, 7, 4]` | 源码检查正确；交互播放未验证 |
| 可视化代码 | 改为 `Node *push_front(Node **head, ...)`，成功分支无返回值；字段改为 `value` | 与原程序的 `data` 字段组合编译失败 |
| 可视化高亮 | 四个状态对应空表及三次完整插入，却用 `[null, 4, 5, 6]` 映射三行不同语句 | 将“插入完成”状态对应到尚未完成连接的代码行，不能称为逐语句执行轨迹 |

可视化代码还附带另一种按返回值更新 head 的调用说明。该说明单独讨论另一种接口时有道理，但放在这份混合接口的示例旁，不能代替与原 C 程序一致的展示。

本次源码片段和编译复核存于 [证据说明](evidence/head-insertion-20261028/README.md)。其中 C 文件由既有页面代码提取，非原始 Provider 响应；没有完整聊天导出或完整 HTML 原件归档，不应将这些材料冒称为可重放的全量实验包。

### 6.3 本轮能得出的结论

- 已观察到良好的概念讲解、正常示例生成和两种错误诊断。
- 已观察到跨产物代码漂移与动作高亮不匹配，证明这类问题仍可能出现。
- EduMind d03 的缺失 `actions` 属于其特定输出契约；本次 DeepTutor 试用未验证同一 Schema，不能计算两者该项成功率。
- 页面当时模型选择器显示 `gpt-6-luna`，不能据此确认每个历史调用的实际模型、参数或上游路由；也不能与 EduMind 的 DeepSeek 结果作同模型优劣归因。
- 页面显示的 token/耗时属于 UI 观察，未核对实际账单或完整调用汇总，不作为费用或 P95 证据。
- 这是小样本功能探索，不能推出长期稳定性、自动审核有效性或课程发布资格。

## 7. EduMind 可借鉴的实现方向

| 方向 | 建议 | 原因 |
|---|---|---|
| 教学交互 | 先做好基于资料的讲解和持续追问，再逐步扩展复杂场景 | 本次试用已体现直接学习价值 |
| 职责分层 | 业务能力组织阶段，工具完成具体操作，持久化服务管理执行状态 | 避免把所有职责塞进一次大 JSON 生成 |
| 上下文管理 | 固定课程约定和示例摘要常驻，详细资料按需检索 | 保持关键约定，控制上下文规模 |
| 来源约束 | 程序提供文档 ID、PDF 页序和原文定位，模型引用已有字段 | 防止没有核实页码却给出确定位置 |
| 出题 | 逐题生成、结构校验、有限修复，保留失败统计 | 缩小失败范围；语义仍需另验 |
| 学情与批改 | 保留未知、部分正确和待澄清状态，记录学生证据 | 避免强行判断掌握或强行判错 |
| 代码与动画 | 冻结一份代码接口、数据结构和执行轨迹，其他产物引用同一版本 | 本轮实际暴露了重新生成造成的漂移 |
| 动作高亮 | 从同一执行轨迹派生状态和代码行映射，独立验证映射 | 最终图正确不足以证明教学步骤正确 |
| 审核 | 区分结构通过、内容正确、跨产物一致和可播放 | 一个总的“生成成功”标记不足以覆盖这些性质 |

不建议直接照搬全部引擎、自由执行工具或任意 HTML 生成路线。DeepTutor 的工具边界不能替代 EduMind 已批准的受约束 DSL、模板隔离和权限契约；采用具体接口或存储设计仍按本项目协议执行。

本文件不调整 PRD、不领取任务、不解除既有质量门禁。[头插协作验证任务交接](../../acceptance/phase-1.5-agent-pilot/PLAN.md)可引用这里的观察作为设计动机；其当前完成状态仍以根 `task.json` 为准。历史 [D02 d03 结果](../../acceptance/phase-1.5-d02-formal-d03/RESULTS.md)和[重评](../../acceptance/phase-1.5-d02-formal-d03/REASSESSMENT.md)保留原结论，本次总结不覆盖其后新增的独立诊断结果。

## 8. 源码索引

以下路径均位于固定提交 `a31d82624c27d75f4e771d4fcb78dce16470b383`；链接不跟随主分支。文件 SHA-256 和本次代码复核命令见 [verification.json](verification.json)。

| 编号 | 文件 | 阅读目的 |
|---|---|---|
| S01 | [AGENTS.md][S01] | 两层工具/能力架构、入口、设置约定 |
| S02 | [web/package.json][S02] | 前端技术栈和检查接口 |
| S03 | [pyproject.toml][S03] | 后端依赖、可选扩展、Python 和许可证声明 |
| S04 | [app/service.py][S04] | 统一持久回合应用服务 |
| S05 | [runtime/turn_engine.py][S05] | 引擎到编排器的执行链 |
| S06 | [services/session/__init__.py][S06] | SQLite / PocketBase 选择 |
| S07 | [agents/_shared/capability_result.py][S07] | 统一结果与用量摘要 |
| S08 | [runtime/bootstrap/builtin_capabilities.py][S08] | 内建能力与工具注册 |
| S09 | [agents/question/pipeline.py][S09] | 出题阶段、修复与失败统计 |
| S10 | [agents/visualize/capability.py][S10] | 专用可视化交付与诊断 |
| S11 | [visualizers/protocol.py][S11] | 插件负载校验 |
| S12 | [LlamaIndex config.py][S12] | 混合检索和重排序配置 |
| S13 | [LlamaIndex retrievers.py][S13] | 检索组合与依赖缺失回退 |
| S14 | [learning/lesson_evidence.py][S14] | 教材来源与引文检查 |
| S15 | [learning/semantic_assessment.py][S15] | 判分、来源契约、指纹绑定 |
| S16 | [course_study/capability.py][S16] | 课程状态与资源按需读取 |
| S17 | [utils/document_validator.py][S17] | 知识库格式与大小限制 |
| S18 | [utils/document_extractor.py][S18] | 聊天附件与提取限制 |
| S19 | [SpaceDashboard.tsx][S19] | 知识中心入口 |
| S20 | [services/rag/pipelines][S20] | 索引引擎实现目录 |
| S21 | [learning/teaching.py][S21] | 教学反馈、偏好与证据 |

[S01]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/AGENTS.md
[S02]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/web/package.json
[S03]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/pyproject.toml
[S04]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/app/service.py
[S05]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/runtime/turn_engine.py
[S06]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/services/session/__init__.py
[S07]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/agents/_shared/capability_result.py
[S08]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/runtime/bootstrap/builtin_capabilities.py
[S09]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/agents/question/pipeline.py
[S10]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/agents/visualize/capability.py
[S11]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/visualizers/protocol.py
[S12]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/services/rag/pipelines/llamaindex/config.py
[S13]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/services/rag/pipelines/llamaindex/retrievers.py
[S14]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/learning/lesson_evidence.py
[S15]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/learning/semantic_assessment.py
[S16]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/capabilities/course_study/capability.py
[S17]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/utils/document_validator.py
[S18]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/utils/document_extractor.py
[S19]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/web/components/space/SpaceDashboard.tsx
[S20]: https://github.com/HKUDS/DeepTutor/tree/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/services/rag/pipelines
[S21]: https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/learning/teaching.py
