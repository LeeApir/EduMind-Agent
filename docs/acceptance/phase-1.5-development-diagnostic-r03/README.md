# T050：严格 Responses Schema 兼容候选 r03

本包只完成新候选的零调用准备。T038 的 r02 仍是 stopped/blocked，未补样本、未重启；本轮新增真实 HTTP/模型请求为0，历史累计为2 HTTP/1生成，未知费用和32k输入/8k输出占额保持。原始结果见 [r02失败报告](../phase-1.5-development-diagnostic-results-r02/README.md)。本包不继承 r02 执行批准、余额、墙钟、用量、通过分子或输出人工核定。

## 修复内容及范围

真实接口曾拒绝原规划 Schema 根层 `allOf`。官方 [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) 说明它只支持 JSON Schema 子集：根为对象，所有字段 required，对象 additionalProperties=false；`allOf/if/then/else` 等组合不支持。以下兼容方案根据该文档和实际错误制定，不声称中转已经接受新包，也没有用新请求探测支持范围。

新适配器保持 `cbbb.fun / gpt-6-luna / Responses / reasoning none`、`store:false`、default 服务档，显式设置 `text.format.strict:true`。仅三个已冻结原 Schema 及原 stage 可使用本适配器；未知关键字、外部/不存在的ref、可选对象字段或未闭合对象都在传输构造前拒绝。

**wire投影不是原 Schema 的等价替代。** wire只采用本包明确列出的保守子集；`allOf/if/then/else`、`contains/minContains`、唯一性、长度、数值范围等完整要求仍由原始完整 Schema 本地强制；`oneOf` 投影为 `anyOf`，排他性仍由原始 `oneOf` 校验。标量 const 转为带类型的单值 enum。每处转换/委托均保留路径、原约束及处理方式，见三个 `*.projection.json`。

新 Prompt 在原可信系统指令后、任何学生输入之前加入完整原 Schema，版本 `p15-strict-wire-v1`。原讲解/规划/审核指令及输入不删改，不把用户内容、预期答案或人工标签提升为系统指令。三个 `*.guidance.txt` 冻结准确附加文本；旧 Prompt/Schema 仍保留原字节。

实际路径是：原请求 → 相同已冻结stage/Schema检查 → wire投影及完整原Schema提示 → 先持久预约、同body输入计数、真实Responses → wire校验 → **原完整Schema校验** → 原调度器机械校验/来源引用/安全/私有可学场景处理。完整Schema不通过时保留真实原件和用量，只交回结构失败，按原已批准预算处理格式修复；不算首轮Schema成功，不由修复补分。未知发送不自动修复或退款。

兼容版本位于新诊断适配器及新入口，不改默认生产Gateway、API、数据库或旧冻结源码。候选真实验收通过也不自动切换生产；阶段退出接线必须使用准确候选版本并遵循原运行开放门禁，不能用本包宣称现有默认生产工厂已经升级。

## 材料、预算和停止规则

34槽及顺序与 r02 完全一致：12支持课程/6画像对、2独立负例、20审核probe。仍使用 Lee 对准确 r01 四份附件的材料采纳登记；未改标签，也没有任何新输出的人工作品核定。H01–H08未访问，旧开发材料不充当独立留出。

新候选只提议**单批次**：最多202生成＋202输入计数请求＝404 HTTP；输入3,440,000、总输出832,000、10,800秒（含人工复核等待）。货币无上限仅是本次待批准提案，r02的费用例外不自动授予新批次。官方参考价不是中转报价，实际费用仍未知。若新包获准，包含既有失败的累计最多406 HTTP/203生成，既有未知占额不退款或折抵。

原逐槽人工复核及质量阈值保持：每槽后等待真人准确输出核对，第二份画像课程才核对准确配对；自然严重错误、unknown、工程/安全失败、时钟/限额、独立性污染、阈值不可达均停止。正确对照误阻断0，严重召回至少9/10、审核精确率≥90%；不补样本、不换模型、不自动开启第二批次。方法沿用 [r02评测方法](../phase-1.5-development-diagnostic-r02/evaluation-method.md)，wire/local区分以本包新增规则为准。

## 新入口与批准门禁

```sh
backend/.venv/bin/python scripts/run_p15_strict_diagnostic.py --start
```

该命令当前必须因没有 r03 准确执行批准而拒绝，拒绝发生在凭据读取、DNS、Docker、PG及输出创建之前。未来批准必须绑定本目录完整 manifest SHA256、`p15-development-r03`、准确limits、scope=`PHASE-1.5-T038`、显式费用例外及真人原始消息，登记本目录 execution-approval.json；不能接受旧 r02 登记。

未来执行只用 `/tmp/edumind-p15-t038-r03` 与专用隔离库 `edumind_catalog_p15_t038_r03`。`--start`一次，`--advance`最多一槽，`--review`只登记真实人工核对。沿用原独立SQLite预约/时钟/不可变收据、PG预算/未知隔离、幂等防重发与所有终止规则。r02目录/数据库/账本不用于新批次。

## 验证与交接

本轮24项离线正负例及3项真实隔离PG/HTTPX Mock联调通过，0失败/skip。三类实际wire都经严格子集检查；对抗样本故意满足wire但违反原条件、来源nullable、唯一性、完整正文、长度、动作等要求，实际适配器本地拒绝并保留计费。PG验证完整四类混合块、已知/未知画像、负例澄清、无预期标签的审核探针，以及Schema/真实原文来源失败后的受限修复；首轮失败仍保留，不补首轮分子。准确证据见 validation.json。

```sh
backend/.venv/bin/python -m pytest scripts/tests/test_p15_strict_schema.py -q
python3 scripts/check_p15_strict_diagnostic.py --check
python3 scripts/check_p15_development_diagnostic_results.py --check
python3 scripts/check_catalog_workflow.py
git diff --check
```

第三条预期退出2：准确证据证明原r02仍blocked。原329份源码/材料和既有私有原件SHA继续复核。Mock和官方文档不等于中转真实通过或教学质量达标。T050完成提交后等待新准确包的真人执行批准；T038保持blocked，T039不领取，无push/merge/部署或生产dynamic开放。
