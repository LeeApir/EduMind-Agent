# T064：最后一次离线语义修复

用户要求“最后一次机会修改这个错误，如果后续还是会出现新的错误，目前方案需要重新评估”。本轮只完成内部离线修复，保持[ADR0039](../../ADR/0039-generation-semantics-and-consistency.md)的私有待复核边界；不修改其历史字节或已批准审核协议。下一次准确冻结的真实复测若出现新的实质性教学/答案错误，即停止追加补丁并重新评估方案，不自动新批或重生成。离线工程通过不作为真实教学质量通过。

先提交315ac88冻结18类开发用例矩阵与已暴露d01原件，再实现。材料是已暴露模型输出和助手编写反例，不是独立留出集/人工真值，未读取封存H。

## 最终行为

- 场景生成v5、服务端语义v2要求：涉及修改程序的题目展示完整准确C变体并指明锚点；明确初始状态、分配成功等前提、观察范围与终止条件。区分函数内部检查点、调用者最终状态、前k次访问、去重可达节点及直到NULL的完整遍历。完整遍历中的自环不能压缩为有限单元素序列。选择题必须包含恰好一个真实结果；不终止/不确定/未定义行为等应如实表达，不能为了有限格式选择错误选项。原输出Schema及题数不变；这些仍是生成约束，不是已执行证明。
- 私有一致性v2识别“完整遍历＋有限答案＋解析声称有环”的来源明确冲突，也对实际显示程序作有界静态指针关系观察。只解析明确的结构体指针、单个自引用指针域、标准分配的准确sizeof(struct)与成功路径、简单指针赋值和已初始化标量复制；跟踪最终返回节点的有向关系，包含自环和两个已分配节点的环。语句/指针数分别限制64/32，沿用每代码块16384字节/3000 AST节点、最多16代码块及报告32768字节等边界。不调用malloc、不运行C、编译器、预处理器、子进程、文件包含或网络。
- 宏、循环、未知调用/分支、外部节点写入有效性、分配大小不明、标量副作用、未知后继等为未评估，不猜测任意C执行、堆有效性或整体终止结果。成功分配分支是显式假设，不证明失败路径安全；文字里的代码修改不被当成实际完整程序执行。解析里的“形成自环”作为候选文本自己的断言，不能冒充C语义真值；仅与同一题完整遍历/所选有限答案对照，保留否定和条件语气。
- 题目范围先分类：函数内部中间状态和明确有意丢弃返回值的题设不再被直接报为调用者更新缺陷；未知意图保留未评估。前k步、去重节点或正确选择“循环不终止”不报有限遍历冲突。真实调用者最终状态的返回值漏接提示仍保留。

所有发现继续为 `confirmed=false` 的待复核建议；`semantic_correctness_verified=false`、覆盖不完整及答案未验证保持。准入事实版本v4只追加新JSON报告，原结构/引用/清洗、草稿可学习权限、评分/掌握度与质量确认权限不变；不授予自动通过、硬拒绝或自动语义修复。

## 验证

实际 **302 passed / 0skip**（XML/SHA见validation.json）：

- backend目录：`.venv/bin/python -m pytest tests/test_free_scene_last_repair.py tests/test_free_scene_consistency.py tests/test_free_scene_markdown.py tests/test_free_scene_semantics.py tests/test_free_scene_answer_contract.py tests/test_free_scene_form_contract.py -q --junitxml=/tmp/edumind-t064-unit.xml`，133项＝新34＋旧99。
- 根目录：`python3 docs/acceptance/phase-1.5-last-semantic-repair-t064/run_pg_offline.py`，169项＝6个实际隔离PG新旧审计/生成契约共存＋54生成＋40准入＋19可用性＋39调度＋11反馈。静态观察未知边界自查后，受影响t020组6项实际重跑通过。专用PG最终exited；运行器使用随机独立库，不读取真实`.env`或调用Provider。
- backend目录mypy检查 `app/services/free_scene_pointer_trace.py app/services/free_scene_question_scope.py app/services/free_scene_consistency.py app/services/free_scene_semantics.py app/agents/free_scene_generation.py app/services/free_scene_validation.py`，6源通过。Ruff检查所有本任务修改的backend Python文件，工作流与diff检查通过。初始类型注解/格式问题已修，未删除或削弱语义断言；代码自查，不宣称独立评审。保留原Starlette弃用及原生成测试3条连接GC警告。

原d01只产生1条真实的自环/有限答案冲突，原4条返回值误报均消除；原r05两类问题仍产生4条原始调用/指针描述发现。见development-observations.json。正确代码顺序、返回前打断环、不同函数/参数名、正确循环选项、前k步/去重、否定/条件措辞、未知分支/分配大小/标量副作用等均有反例。新增约束的payload/原目标/原Schema保持由生成契约回归核对。

新PG用真实6e1aff8历史validator v3和历史consistency v1，不靠旧version标签伪造历史结果：旧4条建议原样保留，新v4只追加1条冲突；原始/清洗正文和答案及摘要相同，owner隔离/幂等/不可更新/head/质量决定保持。另从6e1aff8只读归档运行原d01结果checker，预期退出2确认旧4请求/1unknown/质量失败，见historical-check.json；不改旧manifest去适配当前源码。

## 仍未证明的内容

新真实调用 **0**。没有重新生成或修改旧课程，没有证明下一门课程不会出现新错误；受限规则也不提供完整C语义或任意答案正确性保证。T038继续blocked，原AIAPI推理元数据协议异常仍未放宽。后续若要真实复测，需要新准确包与明确执行范围；本次不继承旧发送预算或重启许可。下一次仍有新实质错误时按用户要求重新评估，不继续逐例补Prompt。无push、merge或部署。
