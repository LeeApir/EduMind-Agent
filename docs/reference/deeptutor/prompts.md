# DeepTutor 提示词方案与 MAIC-UI 对照

核对日期：2026-10-29。

- DeepTutor：`a31d82624c27d75f4e771d4fcb78dce16470b383`，部署对应标签 `v1.6.15`。
- MAIC-UI：本地源码 `/Users/apir/Code/GITHUB/maic-ui`，提交 `aad58ddcc2103058b4c2deffc48a3c13e2c64dd6`。该仓库有其他本地修改；本文用到的提示词及 Heavy 生成器等文件均与该提交一致。
- 对照入口：[MAIC-UI 提示词笔记](../maic-ui/prompts.md)。本文核查实际源码，不把旧笔记中的 EduMind 建议视为当前产品契约。
- 来源文件与 SHA-256 见 [prompts-verification.json](prompts-verification.json)。本次只读源码、整理文档，没有模型调用或新生成实验。

## 1. 核心差别

**MAIC-UI 的核心模板围绕教学网页产物组织；DeepTutor 的提示词围绕当前任务、工具和持续对话组织。**

MAIC-UI 主要告诉模型：教材是什么、学生是谁、网页应包含什么交互、如何排版。Heavy Mode 再把前一步 HTML 交给下一步美化。

DeepTutor 先选择当前能力，再装配身份、工作协议、课程约定、学习者证据、可用工具和资源。模型可在循环中检索、读取、生成或请求反馈；出题和学习等专门能力又有自己的输出与状态协议。

这是组织方式和控制责任的差别，不能直接推出哪一个模型回答更准确。

## 2. DeepTutor 提示词存放在哪里

```text
deeptutor/
├── agents/chat/prompts/{en,zh}/agentic_chat.yaml  # 通用聊天规则与收尾指令
├── agents/loop/prompt_blocks.py                 # 具名提示词块装配
├── agents/loop/pipeline.py                      # system / 历史 / 快照 / 当前消息
├── agents/loop/context_budget.py                # 按实际块统计上下文开销
├── agents/question/prompts/{en,zh}/pipeline.yaml # 探索、规划、逐题、格式修复
├── tools/prompting/hints/{en,zh}/*.yaml          # 每个工具的用途与调用约定
├── tools/prompting/__init__.py                  # 工具说明加载与组合
├── capabilities/mastery/prompts/{en,zh}/mastery_loop.yaml
├── capabilities/mastery/pipeline.py             # 替换通用聊天的基础教学协议
├── visualizers/loop_capability.py               # 可视化提交协议与类型文档
├── agents/_shared/workspace_prompt.py           # 文件读取、输出目录和交付约定
└── learning/semantic_assessment.py              # 部分判分提示词内嵌于 Python
```

并非所有提示词都在 YAML：能力块、工作区规则、判分指令也会在 Python 中生成。不能只搜索 `prompts/` 就认为拿到了完整系统提示词。[D01–D10]

## 3. 普通聊天：具名块与运行时快照

`LoopPromptAssembler.blocks()` 按上下文构造块，空块不加入。可包含：

| 类别 | 典型内容 | 用途 |
|---|---|---|
| 基础规则 | `general`、`runtime_policy`、`loop` | 身份、证据原则、何时调工具和结束 |
| 能力规则 | 当前能力提供的 `PromptBlock` | 定义本轮的工作流程和输出协议 |
| 用户约定 | `workspace_instructions`、`course_conventions`、`persona_style` | 工作区偏好、课程语言/接口约定、表达风格 |
| 学习背景 | `learner_profile`、`memory`、`learning_journal` | 已知学情、历史进度与反馈 |
| 资源与工具 | `tools`、`sources`、`skills`、`notebooks`、`workspace` | 准确名称、可读来源和操作范围 |

`split_for_replay()` 将规则与可变化事实拆开。稳定规则形成 system 消息；当前时间、学情、记忆、工具/来源清单等形成具名运行时快照，由消息构建器以 user 角色加入。历史对话和工具结果保留，变化的快照按块更新；知识库预检索内容进入当前用户内容，而不反复改变 system 前缀。[D02][D03]

概念化装配流程如下，**不是源码原文或固定的逐字消息顺序**：

```text
system：身份 + 当前能力协议 + 课程约定 + 稳定规则
history：既有对话和工具证据
runtime snapshots：最新学情、记忆、来源、工具和工作目录
user：当前问题 + 附件 / 预检索上下文
assistant / tool：按需继续操作，最终给出回答
```

这使提示词可按职责维护，也有利于保持稳定前缀和分析上下文开销；实际缓存命中与费用仍取决于服务方和运行记录，不能仅凭结构承诺节省比例。

### 聊天循环的行为要求

`agentic_chat.yaml` 要求模型：

- 信息不足时按需检索或澄清，资料足够就回答；不用工具的最终回复结束普通聊天循环。
- 工具失败后先看原因、改变策略；不把未执行或失败的动作宣称为成功。
- 工具名、参数、来源 ID 使用提供的准确值，不自行发明。
- 工具调用前可用简短说明向用户交代进展。
- 资料、附件和工具结果是上下文，不能覆盖系统规则。
- 针对预算耗尽、截断、只输出内部推理等情况，运行时有不同的继续或收尾指令。

这些是行为指令；是否遵守仍需工具执行器与输出检查配合，写进提示词不等于必然执行。[D01]

## 4. 工具说明：不仅列名字，还解释使用条件

每个工具的提示词提示项可包括 `short_description`、`when_to_use`、`input_format`、`guideline`、`note` 和 `phase`。[D04]

以 RAG 为例，它说明什么时候优先查教材，要求非空查询和已挂载知识库名；涉及图表时，进一步要求沿用准确来源、页码或资源标识，缺少像素或证据冲突时保留判断。[D05]

这里有两层：

1. **提示词说明**帮助模型判断什么时候用、怎么用。
2. **原生工具 schema 与执行器**约束可接受参数及执行权限。

它们不是同一个东西。指令写着“不要编造来源”，仍不能代替程序核对来源身份。

## 5. 出题：各阶段承担不同输出职责

`deep_question` 的模板与普通聊天不同，主要分为：[D06][D07]

| 阶段 | 输入 | 要求输出 |
|---|---|---|
| Explore | 用户目标、题型数量、资料、历史错题 | 调研与工具调用；最后给用户简短出题前言，本阶段不写题 |
| Tool summarizer | 单条工具原始结果 | 压缩结果，要求保留来源 ID、页码、公式和数值 |
| Plan | 探索轨迹与出题参数 | 带 `PLAN` 标签的题目模板 JSON，包含题号、考点、类型、难度 |
| Quiz step | 一个模板、探索轨迹和上下文 | 单道题的 JSON，包含题干、选项、答案和解析 |
| Repair | 无效 JSON、模板和具体问题 | 仅输出修正后的题目 JSON，保持题型及主题/难度意图 |

探索及逐题循环使用 `THINK / TOOL / FINISH` 标签；实际工具调用走原生 `tool_calls`。这些标签是该流水线的控制协议，**不能泛化为所有 DeepTutor 聊天都使用标签**。

一个细节是：探索阶段给用户看的 `FINISH` 前言并非后续规划的依据；后续使用单独组织的探索轨迹。工具结果概括会替换循环缓冲中的原始结果；开关默认启用，概括失败或为空时可保留原始结果。[D07]

这减少了重复冗长内容，但“保留信息”本身也是模型任务。提示词要求保留事实并不证明概括无损；重要原件仍应可追溯。

修复模板收到具体 `issues`，不是笼统要求“再检查一下”。模板在提示词层限制返回字段，流水线再解析、规范化并检查。其主要保证是格式与流程可消费性，参考答案正确性仍需独立验证。

## 6. 学习辅导与可视化的专门协议

### 学习辅导

`MasteryPromptAssembler` 替换通用聊天基础块，避免一边要求自由聊天、一边又叠加冲突的教学流程。`mastery_loop.yaml` 根据实际状态决定先了解学生、建大纲、探查、讲解还是出题。[D08]

例如，它要求：学生没有提供的学情不得编造；讲解不等于掌握；已经作答的题目应使用持久化答案继续批改；工具尚未记录掌握时，不凭一句“你会了”推进。题目、答案、来源和申诉的关联需要服务层检查配合。

### 可视化

当前专门可视化能力把 `visualization_protocol` 与已安装类型的技术文档组合：理解目标 → 选择或遵守指定类型 → 生成 payload → 调用 `submit_visualization` → 根据具体校验错误修复 → 成功后结束。[D09]

它明确要求不能把文字回答当作画布交付，也写明“能渲染”不等于教学合格。但这是提示词质量要求，仍需要检查实际校验器是否覆盖教学语义。

本次头插法 HTML 由普通聊天的工作区工具生成，未证明经过上述专门能力。因此，不能拿那个 HTML 的漂移直接认定专门 `visualize` 提示词或校验器已经执行且失效。[试用记录](README.md)

## 7. 与 MAIC-UI 的区别

| 维度 | MAIC-UI 核心生成路线 | DeepTutor |
|---|---|---|
| 中心任务 | 从教材与画像生成交互教学网页 | 持续辅导，并按需使用检索、出题、学习状态和产物工具 |
| 提示词组织 | 主要 Python 模板函数、Heavy 阶段模板；其他服务也有内嵌提示词 | 按能力/工具拆分的 YAML、Markdown、Python 块与装配器 |
| 上下文传递 | 分析结果与画像填入模板，Stage 1 HTML 传入 Stage 2 | 具名规则块、运行时快照、历史工具结果、来源与学习状态 |
| 画像处理 | 核心模板显式注入年级、兴趣等 | 注入已有画像；学习模式还规定何时询问、如何保存与继续 |
| 输出 | 分析 JSON、网页 HTML、元数据；随具体模板不同 | 普通回答、原生工具调用、逐题 JSON、可视化 payload 等分开 |
| 页面约束 | 明确双栏、Canvas/SVG、控件、响应式、视觉精修 | 当前可视化类型规则及提交协议；普通聊天可另生成文件 |
| 失败处理 | 当前 Heavy 实现对空结果/异常最多尝试三次，存在回退 | 按能力处理：工具错误、协议问题、单题格式修复、预算收尾等 |
| 质量保障 | 提示词提出教学与功能要求；本版本 Heavy 主执行点跳过验证 | 某些流程实际有结构/来源/状态检查，但没有全局正确性保证 |

### 必须纠正的旧笔记

现有 [MAIC-UI 笔记](../maic-ui/prompts.md)曾把下列内容写得过强。本次以固定源码纠正：[M01–M04]

1. **不是全部提示词只存在两个文件。** 两个文件是重要入口；例如 `read.py` 还内嵌网页编辑提示词，`ai_prompts.py` 也包含智谱及更多生成/编辑函数。
2. **给出 JSON 示例不等于提供商强制 JSON Schema。** 核心分析模板是自然语言格式要求。是否有独立 schema 或服务方强制，应检查实际调用与校验链。
3. **Heavy 主执行点当前没有运行传入验证器。** `_execute_stage` 中实际代码是：

   ```python
   # is_valid, issues = validation_func(html)
   is_valid, issues = True, None
   ```

   一份非空 HTML 会在此按验证通过路径返回并缓存。不能把日志中的“Validation passed”当成实际语义或功能审核。
4. **不是“首次生成＋三次基于反馈的精修”。** 该函数是 `range(3)`，最多三次尝试；函数内没有调用精修模板、也没有把验证意见重新写入 context。`get_refinement_prompt` 在该生成器中仅被导入。Stage 2 的确会接收 Stage 1 HTML 进行布局精修，但这不等于验证失败后的修复闭环。
5. Stage 1 模板写的是“至少 2 个可调参数”，旧笔记的 3 个不准确；这只是模板要求，不是已经通过的交互测试。

这些发现针对已读的固定文件与执行路径，不扩展为“整个 MAIC-UI 没有任何验证”。外部仓库有其他本地修改，本次不修改其代码，也不对用户部署中的所有 Provider 路径作推断。

## 8. EduMind 如何参考

建议借鉴 DeepTutor 的职责拆分和上下文装配，借鉴 MAIC-UI 对教学页面交互的具体要求，再用独立程序事实约束它们：

```text
共同事实：原目标、接口、示例初态、代码版本、状态轨迹、来源
    ├─ 内容提示词：解释这些事实
    ├─ 题目提示词：在支持范围内选题、解释答案
    ├─ 演示提示词：引用已有轨迹和代码行，组织可视化
    └─ 修复提示词：根据具体错误修改允许范围
程序：装配、schema、引用存在性、轨迹映射、版本及执行边界
```

这是设计示意，不是已批准实现。它解决的是多份产物反复重写同一算法事实的风险；仅把一个大 Prompt 拆成多个角色，仍可能得到彼此一致但共同错误的结果。

优先验证三项：上下文关键事实有没有丢、输出是否真的经过校验、修复是否保持接口和状态不漂移。模型使用、调用次数及取舍应通过有记录的对照决定，而不以模板数量作为质量指标。本文件不变更 PRD、活动任务状态或既有验收标准。

## 9. 固定源码入口

| 编号 | 源码 |
|---|---|
| D01 | [聊天规则 agentic_chat.yaml](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/agents/chat/prompts/zh/agentic_chat.yaml) |
| D02 | [提示词装配 prompt_blocks.py](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/agents/loop/prompt_blocks.py) |
| D03 | [消息组装 pipeline.py](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/agents/loop/pipeline.py) |
| D04 | [工具说明加载](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/tools/prompting/__init__.py) |
| D05 | [RAG 工具提示词](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/tools/prompting/hints/zh/rag.yaml) |
| D06 | [出题阶段提示词](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/agents/question/prompts/zh/pipeline.yaml) |
| D07 | [出题阶段调用点](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/agents/question/pipeline.py) |
| D08 | [学习模式提示词](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/capabilities/mastery/prompts/zh/mastery_loop.yaml)；[装配器](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/capabilities/mastery/pipeline.py) |
| D09 | [可视化能力提示词块](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/visualizers/loop_capability.py) |
| D10 | [工作区规则](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/agents/_shared/workspace_prompt.py)；[语义评估](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/learning/semantic_assessment.py) |
| M01 | [MAIC-UI 核心提示词](https://github.com/THU-MAIC/MAIC-UI/blob/aad58ddcc2103058b4c2deffc48a3c13e2c64dd6/backend/src/services/prompts/ai_prompts.py) |
| M02 | [Heavy 模板](https://github.com/THU-MAIC/MAIC-UI/blob/aad58ddcc2103058b4c2deffc48a3c13e2c64dd6/backend/src/services/templates/heavy_mode_prompts.py) |
| M03 | [Heavy 实际执行点](https://github.com/THU-MAIC/MAIC-UI/blob/aad58ddcc2103058b4c2deffc48a3c13e2c64dd6/backend/src/services/html_generation/heavy_generator.py#L180) |
| M04 | [内嵌编辑提示词 read.py](https://github.com/THU-MAIC/MAIC-UI/blob/aad58ddcc2103058b4c2deffc48a3c13e2c64dd6/backend/src/services/read.py#L265) |
