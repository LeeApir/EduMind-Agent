# T037 最终开发诊断准备包 r02

本包完成 T037 的零调用准备，不是 T038 执行批准，也不证明模型教学质量合格。用户要求完成当前任务后停止。实际 Provider 请求为 0，生产仍为 catalog_only；不领取 T038、不开放动态、不 push/merge/部署。

候选为用户指定 `.env` 的公开配置：`https://www.cbbb.fun/v1`、`gpt-6-luna`、Responses JSON Schema、reasoning `none`、`store:false`、Standard/default 服务档。最新版是用户选择的别名，不伪造日期快照；中转的版本映射和发票未独立验证。返回 model 不准确匹配、计数接口不可用或总 usage 不可核对，立即停发，不换模型或传输协议。

官方型号/总输出计量依据见 [official-reference.json](official-reference.json) 及其中直接文档链接。官方 USD 价只作参考，不能冒充 cbbb 报价或实付。用户明确“价格无上限”，本次提案取消货币上限；仍严格限制单候选、单批次、404 次 HTTP（最多 202 次生成，另最多 202 次 `/responses/input_tokens`）、输入 3,440,000、总输出 832,000、总墙钟 10,800 秒。失败、修复、计数请求、未知发送都计入；不追加探测、第二批次或第二候选。人工等候也计入墙钟。未知费用不按零结算，收据中实际中转费用保持 null。

原 r01 维持原字节，只是历史准备记录；其中 30 CNY/202 请求旧提案由本包取代，旧 manifest 的源码漂移不能当作当前包通过。准确文件以本目录 `manifest.json` 的 SHA256 为准。

## 材料与人工来源

12 课程/6 画像对、2 负例、20 probe 沿用用户实际审阅的 r01 准确附件。材料由助手起草、Lee 明确采纳；原始回答、四份附件 SHA、自报耗时 `1h` 记录在 [user-direction-and-material-approval.json](user-direction-and-material-approval.json)。不推算人工起止时刻，不将采纳冒充人工原创或独立盲测。

`manifest.json.slots` 冻结顺序、开发输入、预期及 10 严重/10 正确标签。标签和答案不进入 probe 请求，只传片段；离线实际 wire 测试验证这一点。H01–H08 继续封存，未读、未调优；旧 A/G/P/D 不充当独立留出集。

## 执行与人工检查点

只有未来准确 T038 批准后，才可人工登记本目录 `execution-approval.json`，包含 scope、整个 manifest 原始字节 SHA256、batch_id、准确 limits、fee_cap_waiver、human_message、reviewer、received_at、evidence_ref。本工具没有生成或自批批准的命令。该登记不属于当前冻结输入；收到新的真人批准后才可建立。

当前运行以下命令必须拒绝，且拒绝发生在读取凭据、DNS、Docker、PG 和输出目录创建之前：

```sh
backend/.venv/bin/python scripts/run_p15_development_diagnostic.py --start
```

未来获准后，固定独立目录 `/tmp/edumind-p15-t038-r02`、专用标记容器 `edumind-phase1-t037-pg` 的 loopback 15437 和数据库 `edumind_catalog_p15_t038_r02`。`--start` 只建立一次持久批次，`--advance` 最多运行一个槽，`--review /absolute/human-review.json` 只登记人工判断。多执行者文件锁拒绝并发。所有目录含私有评测原件，不得进入产品接口或 Git。

真实创建经 Scheduler.enqueue 读取同 owner 画像（T049），再由原调度器执行规划/逐场景生成；保留原有每课程 13 次生成、200k 输入、48k 输出、600 秒、格式修复与未知发送规则。独立 SQLite 账本在发出前持久预约，原 PG 账本照常存在。每次实际生成前使用同一准确 body 请求输入计数，计数超过 32k、输出上限超过 8k、返回用量与计数不一致都停止。总输出含推理及其他不可见生成 token，不只累计可见正文。

收据保存准确 wire body、计数响应、模型响应、SHA、usage、参考费用；不保存鉴权头。响应回显密钥时不落原文，只留停止类型及账本未知占额。HTTP 非成功、坏模型标识、缺 usage 等安全可保存原件仍保留；未知发送不退款、不自动重试。PG 规划/场景/尝试/结算/事件快照随课程输出保存，异常中断时保留 PG 与 SQLite 原账本供人工恢复；原进程中断槽不自动重发。

计划出现时、首个场景生成前冻结 n，必须落在人工采纳的 1–8 场景范围内。计划失败按预先声明上界记录未运行场景，不缩小分母。正常课程未完整 succeeded 即工程失败。负例只接受原协议的 awaiting_clarification；若规划了不支持目标，首场景前停止。负例不进入支持域课程成功率。

每个槽输出后必须先人工检查，才允许下一个槽。报告绑定 slot_id、准确 output_sha256、reviewer、reviewed_at、evidence_ref、exhaustive_coverage_attested、natural_severe_errors 和非空 items；每项有 area/location/reason/verdict，verdict 仅 pass/fail/unresolved。工具不预填 pass，也不把模型输出当人工真值。课程必查 requirements、learnability、facts、answers、profile；每对第二份额外查 pair，并以 pair_output_sha256 顺序绑定两份准确输出。第一份不提前伪造配对判断。

probe 报告额外填写 severe_detected、flagged_correct_control、findings_total、findings_true；命中必须给 matched_issue_quote。真人判断必须匹配预植入的具体错误，泛泛怀疑不能算召回。人工 unresolved、工程失败、自然严重错误、输出被替换、费用/计数/时钟异常、独立性污染均停发；不补样本。两个严重样本漏检或一个正确对照误阻断即不再达到门槛；允许一个漏检，20 项后精确率必须 ≥90%。

## 逐项评测与判定

评测方法详见 [evaluation-method.md](evaluation-method.md)。人工输出报告目前不存在；不得把输入采纳或离线 Mock 当成 T038 真实结果。即使所有槽工程完成，也必须逐项计算全部质量指标、保留失败/未运行/未知并由人决定候选去向；本工具不自动发布或创建产品签核。

## 准备验证

```sh
backend/.venv/bin/python -m pytest scripts/tests/test_p15_diagnostic_ledger.py scripts/tests/test_p15_diagnostic_transport.py scripts/tests/test_p15_diagnostic_execution.py -q
python3 scripts/check_p15_development_diagnostic.py --check
python3 scripts/check_catalog_workflow.py
git diff --check
```

实际 PG/Mock 联调需通过 `run_catalog_db_tests.test_environment` 创建新的 `edumind_catalog_p15_t020_*` 测试库后执行 `backend/tests/test_p15_diagnostic_execution.py`。准确本轮原始 XML/日志摘要见 [offline-results.json](offline-results.json)。早期夹具枚举失败也登记，不删除或冒充通过。测试中的 TEST_ONLY 批准仅临时目录内的合成数据。

交接：本任务交付只到冻结准备包与离线验证。后续 T038 必须先获得这个准确包和预算的真人执行批准，再领取任务；本次完成提交后停止。
