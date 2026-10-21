# 四项完整生成小验收 r01（仅冻结，未授权执行）

T073 浏览器证据完成后，T074 冻结本独立提案与执行器。当前真实请求授权为 **0**；没有初始化运行、生成新课程或恢复旧槽位。准确执行授权须绑定本目录 manifest 的 canonical SHA256，并另存 `run-approval.json`；`approval-template.json` 不是授权。

本轮只回答：A01/A02 的定向修复及四条完整生成服务链路是否值得继续验收。它不是正式独立测试集，也不替代 T040 的 Schema≥98%、自动正式成功≥95%、严重错误召回≥90%。T040 保持 blocked，T041/T042 和生产 dynamic 不开放。

## 材料、配置与链路

顺序固定 A01 数组求和 → A02 链表头插 → A03 栈 → A04 循环队列。`cases/` 原文与原目标快照不改，A02/A03 沿用此前用户指定节点的人工澄清；自动解析歧义仍保留。`labels.json` 是交互 GPT 的验收检查表，未经独立真人重新签核，不冒充独立真值。

生成固定 DeepSeek `deepseek-flash / none`，审核固定第三方兼容渠道 Luna `gpt-6-luna / high`。精确出站配置见 `configuration.json`：计划输出2048、资源4096、审核8192、单请求60秒/连接5秒、单操作180秒/20请求、每资源最多两次业务修正；无网络重试、回退或额外评分 API。生成 v9、场景 v2、审核 v4.10、程序证据索引 v1 及完整政策摘要均绑定。

执行器从冻结的 `PlanInputs` 开始，运行实际服务的共享计划、三个场景生成/审核、完整单元审核、隔离 PostgreSQL 持久化与正式发布/待人工分流。它不重测 HTTP 画像/路径建立，不执行新生成 C。首计划实际适配器 wire 已离线捕获；后续请求依赖真实父输出，只能在获批运行时逐条绑定并保存，不能预先虚构。

浏览器三态与读取边界复用 [T073 证据](../phase-1-browser-evidence-r01/README.md)。正式页使用已有工程夹具，不计模型质量成绩。旧 U/R 的具体结果及跨版本边界列在 `reuse-matrix.json`：不重复独立筛选，不把旧 v4.9 审核当作新内容/v4.10 的批准。每份新生成资源仍必须实际审核。R02 冲突、旧 A01 不足、A02 无据拒绝及单次复测 pass 全部保留。

## 准确预算与时钟（待批准）

| 约束 | 数值 |
| --- | --- |
| 正常请求 | 32：16生成＋16审核，每项8次 |
| 硬上限 | 48：共享额外16次，不回收未用基础槽 |
| 分模型上限 | 生成24、审核24 |
| 生成阶段上限 | 计划4、资源20 |
| 输出 Token 上限 | 286720＝4×2048＋20×4096＋24×8192 |
| 费用 | 沿用不限政策；输入 Token 由真实父输出决定，不能事先给准确总量/账单 |
| 新运行时间 | 获批后 init 才建立 T0；45分钟停新请求，60分钟硬截止 |

这是独立的新60分钟预算提案，不能沿用“继续”初始化，不能重置旧5小时截止或恢复旧失败账本。实际用量、未知用量及失败均保存；任何预约也占槽，无自动补发。

## 计分与停止规则

逐项分别记录技术完整性、核心判断、所有附带断言、所有引用、完整质量及修正传播影响。审核模型的 pass 不是 GPT 的质量结论；GPT 的静态复核也不是运行安全证明或独立真人签核。

- 完整质量通过要求自动 `completed`、本地单元 `pass`、目标/教学/题目均满足，全部断言和引用有据，且检查所有候选及修正历史。题型不能直接决定过程测量是否成立；只承诺三道过程题时逐题检查，不强加三题都重复完整轨迹。
- `needs_human`、人工批准、未运行、审核只拒绝正确但有错误附带建议，均不进入自动完整质量分子。A02 明确承诺的细化状态测量若仍缺失，不能因三题涉及过程就改为完整 pass。
- 附带错误若未进入修正且仅低风险，完整质量仍失败；A03/A04 可容许最多一条此类失败或合理待人工。无据严重拒绝、严重漏检或错误反馈进入修正为红事件，立即停止。
- **A01、A02 均必须自动完整质量通过，任一失败即停**，不继续 A03/A04。所有技术完整性失败即停。完整质量失败超过1条、3/4不可达即停。
- 四项全部核对后，A01/A02通过且总计至少3/4自动完整质量通过，才标记本小验收合格；其余保留实际失败。这个小样本阈值是本提案的准入筛查，不降低正式 T040 标准。

每次 run 后停在 `awaiting_gpt`，先按 `evaluation.schema.json` 写完整评测记录，再 assess 才能下一条。不得只看最后单元结论：所有请求/回包、资源审核、修正及单元审核都要检查，逐项列全部断言/引用和证据。记录必须绑定实际结果、原文/标签、全部工件摘要与实际用量；评测不完整不得续跑。歧义无法裁定则留待人工并停止依赖推进，不悄悄改标签。

## 离线验证与执行接口

`offline-executor-check.json` 记录16项通过、0跳过：真实独立 PostgreSQL 加 MockTransport，四个完整服务流程每条8次实际适配器请求，路由/证据、限额、时钟、授权、评分存盘及伪造用量拒绝均覆盖。脚本模型输出和工程评分仅验证执行器，不证明真实模型语义修复。

零调用检查：

```sh
backend/.venv/bin/python scripts/run_generation_mini.py check
backend/.venv/bin/ruff check scripts/run_generation_mini.py scripts/tests/test_generation_mini.py
python3 scripts/check_catalog_workflow.py
```

将来仅在本 manifest 获得准确新授权、保存实际用户授权原文后，才可按序 init、run、评测、assess：

```sh
backend/.venv/bin/python scripts/run_generation_mini.py init
backend/.venv/bin/python scripts/run_generation_mini.py run --case A01
backend/.venv/bin/python scripts/run_generation_mini.py assess --case A01 --evaluation /absolute/path/to/actual-evaluation.json
backend/.venv/bin/python scripts/run_generation_mini.py report
```

不得创建占位授权。真实账本/请求/回包只存忽略的 `local-materials/phase-1-generation-mini-r01/`；不提交凭据、完整环境或推理原文。执行库固定 `edumind_catalog_generation_mini_r01`，首次初始化必须为空；旧库不改。后续材料/源码/配置改变须新冻结，不修改历史证据摘要来绕过校验。

交接：T073提交 `cfd9930`；T071/T072为 `2dc21b3` / `6205602`。本任务只完成可审查的准备和执行器，不领取 T040、不发送模型请求。最终冻结根由 `check` 输出及 `validation.json` 中独立校验结果确定；manifest 不包含自己或未来授权文件。
