# 生成与审核分离诊断 r01（零调用准备）

本包与[四类固定缺陷材料](../phase-1-defect-regression-r01/README.md)配套，不改当前生产生成/审核Prompt、Schema、策略或模型。旧失败、停止和未运行项均保留。这里交付可注入Gateway的独立探针、零网络入口、评测记录和诊断计划；**不是已授权的真实执行包**，不沿用mini-r01剩余40槽。

## 两路怎么分

| 评估 | 输入与调用 | 要回答的问题 |
| --- | --- | --- |
| 审核 | 固定12份完整材料，每次只调用review_once一次；原文、计划、学生内容、锚点不变 | 相同输入下，模型结论、具体缺陷、附带断言、引用是否波动？ |
| 生成 | G01–G04四份原始目标，独立生成计划＋讲解＋代码＋练习，每份4次生成 | 计划是否自洽/忠实于原要求？正文是否正确且落实目标/过程测量？ |

`fixed_review` 不调用生成、不修正；其实际适配器wire与T075捕获逐字相同。`generation_draft` 不调用ReviewAgent、不写数据库、不发布；所有结果标`not_reviewed`，不是正式课程成功。内部workspace暂借needs_human门状态允许后续草稿构造，不创建ReviewRecord或产品人工决定，也不伪造审核pass。

生成侧使用原A01–A04的同一原文/目标快照，以G01–G04新ID表达新的研究输入，不恢复旧A运行。它们不是独立盲测材料；与固定审核12份材料不共用真实生成结果，不把新生成数据悄悄替换审核回归样本。

两路由IsolatedGateway在发送前限为1/4调用，禁止跨路和retry_safe。没有内置Key/环境读取或live/run/init入口。未来真实Gateway还必须接持久台账、出站证据、超时、摘要绑定和准确授权；只有离线capture入口不能发真实请求。

## 记录与证据边界

审核记录模板见 `review-observation-template.json`，空表见 `review-observations.json`。每条绑定case与wire摘要、固定重复编号1..3、技术结果/原回答、评估人及逐条断言/引用核对。技术失败必须保留为observed attempt，语义留unassessed；未发送保持not_run，不能从分母消失。摘要不同、重复槽、Mock与真实证据混用、缺断言、漏引用、错字段原文、无据断言却标pass都会被拒绝。

汇总逐材料显示三个verdict的频数、是否变化、标签匹配数、完整语义核对匹配数、技术失败、未决和未运行。required_claims必须同时检查labels中的严重类别/影响及禁止的无据推断；all_assertions/all_citations另列，不能只看核心拒绝。语义结论由外部逐项核对者提供，汇总器只验证完整性/引用位置并计数，不自己充当语义裁判，也不能凭一份被标记externally_audited_provider的JSON证明其Provider来源。真实原件、路由、用量和签核仍须未来执行器验证。

生成记录使用 `generation-checks-template.json`。计划内部一致、原文忠实、事实安全、教学交付、练习测量五项分别填status/reason/source_pointers；标pass/fail必须有解释及真实草稿JSON位置，不能只填总分。汇总绑定草稿摘要，正式成功与审核模型质量字段均为null。格式/schema通过、模型自称正确、某次ReviewAgent pass都不能证明这些语义。

Mock探针中的脚本计划/正文只用于检验真实适配器和流程，即便不满足目标也不构成质量评测样本或成功。`offline-lane-checks.json`保留来源和明确限制；没有生成真实课程。GPT复核并非独立真人真值。3次重复只能观察小样本波动，不能保证稳定或推断代表性错误率；固定/盲测、历史/当前、生成/审核成绩均不混算。

## 待冻结的有界真实计划建议

这只是下一执行包的候选排期，**真实授权仍为0**，不请求基于当前草稿执行。

- 审核：同12材料固定做3轮，每轮按case-index顺序各一次，合计最多36次Luna high/8192/60秒；输出上限294912。重复编号及顺序预先固定，不因某次通过/失败额外补测，也不“跑到连续通过”。
- 生成：四目标各计划1＋资源3，合计最多16次DeepSeek none；计划2048、资源4096、单次60秒/操作180秒；输出上限57344。不调用审核、不修正、不进入正式发布。
- 两路合计最多52次、输出上限352256，无网络重试/回退/额外judge API；费用沿用不限偏好，输入依实际父输出变化，不能精确预报。两路预算独立，不挪用剩余额度。
- 技术失败、严重错误漏检、无据严重拒绝或错误反馈传播触发该路停止并保留未运行项。普通教学不足/非严重附带错误按已冻结顺序观察，全部记失败，不为取得通过换模型/改材料/调Prompt。生成侧发现普通计划/内容错误只记录该项维度，不变更输入再测；新C不执行。停止后的频数只报告已观测/未运行，不声称完整样本频率。
- 真实执行前还需绑定每路当前源码/配置/材料、持久账本、准确预算和时钟，并由用户批准。两路完成后才判断是否重新准备T040正式准入；原98%/95%/90%阈值不变。

## 零调用入口

```sh
# 只捕获一条固定审核请求（Mock）；不会生成课程
backend/.venv/bin/python scripts/prepare_separated_diagnostics.py review-capture --case plan-consistency--error
# 只捕获四条独立生成请求（Mock）；不会调用审核或发布
backend/.venv/bin/python scripts/prepare_separated_diagnostics.py generation-capture --case G01
# 只读汇总外部逐项核对记录；当前空表36项全为未运行
backend/.venv/bin/python scripts/prepare_separated_diagnostics.py review-summary --records docs/acceptance/phase-1-separated-diagnostics-r01/review-observations.json
# 只读生成草稿维度评估
backend/.venv/bin/python scripts/prepare_separated_diagnostics.py generation-assess --draft /absolute/path/to/draft.json --checks /absolute/path/to/checks.json
```

验证：28项独立两路/计数/篡改/引用/失败保留回归，加T075的17项共45项通过。测试含完整12审核实际Mock wire和4生成实际Mock流程；没有真实Provider质量结论。没有修改Web、产品数据模型、生产审核指令或开放dynamic。
