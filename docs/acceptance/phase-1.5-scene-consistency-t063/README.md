# T063 跨内容一致性检查交接

按用户明确指令完成T062之后的第二项内部改进，边界见[ADR0039](../../ADR/0039-generation-semantics-and-consistency.md)。新增 `free-scene-consistency-v1`；准入审计升级 `free-scene-hard-gate-v3`，在既有私有 `FreeSceneValidation.findings` 记录报告，无迁移、公共接口或权限变化。

检查当前及实际必要上游的专用C代码块、说明、题干、解答和可视化说明。受限AST关联明确声明的接口，观察返回新头却丢弃返回值、局部传值指针与调用者永久失去入口的描述、同名接口约定冲突。每条建议包含规则版本、准确字段指针、原文、关联代码SHA及上游版本/摘要。参考答案仅绑定原始摘要与关联题干发现，永不标为答案已验证。

原D02第二场景保留为已暴露的合成开发回归，不使用封存集或真实学生。能定位原两类问题，并覆盖函数/参数改名；正确接回、括号/类型转换接回、二级指针更新、注释/字面量及明确有意错误例子的反例已验证。测试中修正文案与调用仅用于反例，不改历史课程或答案。

检查只在内存解析，不运行C、预处理器、子进程、文件包含或网络。最多16代码块、64函数、24发现，代码大小/AST节点受T062边界限制，最终报告不超过32768字节。宏、扩展、复杂上下文、未覆盖语言/语义及超限保留未评估；Markdown中的代码围栏不当作专用代码块解析。文字线索和接口模式可能漏报/误报，不能证明运行结果、内存安全、任意答案正确或跨内容完全一致。`coverage.complete`、`semantic_correctness_verified`、`answer_verified`均不能据此变真；未发现仅表示支持规则内没有观察到冲突。

报告为私有待复核建议，`confirmed=false`。机械结构、引用、清洗、原始与清洗正文/答案不变；不拒绝草稿、不改变可学习权限、不创建质量确认、不授予评分/掌握度、不触发模型修复，也不把建议当成机械失败确认依据。实际历史97130f5的v2与新v3同候选并存已通过PG测试：只追加、摘要/清洗完全相同、不可更新、owner隔离和幂等、head与质量决定保持。

实际 **211 passed / 0skip**，命令与XML/SHA见 `validation.json`、根task.json：

- backend目录pytest：`tests/test_free_scene_consistency.py tests/test_free_scene_markdown.py tests/test_free_scene_semantics.py tests/test_free_scene_answer_contract.py tests/test_free_scene_form_contract.py -q --junitxml=/tmp/edumind-t063-unit.xml`，99项（新24、旧35+17+13+10）。新增用例禁止网络/子进程，并验证无header/文件读取。
- 根目录 `python3 docs/acceptance/phase-1.5-scene-consistency-t063/run_pg_offline.py`：专用隔离PG/Mock共112项，分组3（新审计、原清洗、原语义版本共存）、40准入、19可用性、39调度、11反馈。仅现有测试容器和独立随机数据库，不读真实`.env`、不调用Provider。要求本地专用容器已就绪；本次结束后已恢复exited。
- 相关8文件Ruff、3源mypy、工作流和diff检查通过；完成代码自查，不宣称独立评审。Markdown的两处str注解只修类型推断，不改变运行清洗逻辑。

初测两个带括号/转换接回写法误报，通过修检查实现消除，原断言保留。PG旧测试残留v2后缀查找改为已断言的准确当前版本，原摘要等式保留；旧“findings为空”改为严格断言唯一未评估报告、报告无缺陷、无语义验证和执行，原机械/清洗断言保留。全部受影响分组实际重跑通过，失败不计入通过数。

真实Provider请求 **0**。旧r05、单次sol、unknown、封存H、冻结材料和历史失败不改，新源码不能通过改旧SHA冒充旧包有效。T038仍blocked；生成Prompt与检查机制的离线通过不代表模型输出已改正。后续若继续课程诊断，须另准备当前源码对应的接线、准确执行包与授权范围；本轮不启动真实调用、自动语义重生成、push/merge或部署。
