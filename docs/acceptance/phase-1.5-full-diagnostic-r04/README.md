# T038 完整开发诊断 r04 准备包

**未真实执行，批准登记为false。**基线T059提交d9b3fa0；具体A—C见[ADR0037](../../ADR/0037-full-development-diagnostic-recovery.md)。旧r03、r02等均停止，不是恢复或补跑旧批次。

## 准确范围

- 原始slots.json字节不变：12课程/6画像对，2目标边界负例，20审核探针；同一候选组合、单批。标签及来源不改；不是未见独立集。
- 生成：DeepSeek官方 `https://api.deepseek.com/responses` / `deepseek-flash` / none；Prompt free-course-plan-v1、free-scene-generation-v2，准入free-scene-hard-gate-v2。
- 审核：AIAPI `https://aiapi.world/v1/responses` / `gpt-6.1-sol` / low；场景review-v2，probe原PROBE_PROMPT及resource-review-v3不变。
- 新最多250 HTTP/3小时（含助手复核）：生成182，审核68（最多48场景＋20probe）；旧10请求保留，累计最多260。每课13生成/600秒、每请求120秒并受绝对截止约束。token/金额不限是待批准提案；实际收费/币种未知，不能保证客户端取消后停止计费，不能把请求8000参数当服务硬界。
- 仅合成材料：生成请求目标/画像自述等；审核请求课程目标、计划、正文、私有参考答案、动作及必要上游。无真实学生、旧签核课程、H封存内容；第三方留存和完整上游上下文未独立验证。禁回退/重定向/未知重发/自动新批/补样本。

## 执行与人工来源

`backend/.venv/bin/python scripts/run_p15_full_diagnostic_r04.py --check`只核对冻结文件，不读Key、DNS、PG或创建真实目录。

准确批准后，显式`--step`每次只推进一个新槽或尚未审核的场景；在助手检查点停下。`--review <报告.json>`导入由助手实际阅读产生的证据，不自动编造报告。场景非pass时，需先实际核对；准确误报可用`--adjudicate <裁决.json>`登记后续审，真实错误则导入失败报告并停，不能假记误报或人类真值。对已有slot_output不改字节。

报告要求：原有requirements/learnability/facts/answers/profile及必要的pair覆盖；课程还要逐块atomic_facts引用/结论/理由、每题answer_checks原答案与精确评分允许/拒绝输入；对全部非pass场景意见绑定model_adjudications和opinion SHA。实际复核仍是Codex assistant/delegated_assistant，非独立人类标签，不赋予产品答案核定或发布资格。

`--assessment`只读SQLite快照事务与已保存证据，验证请求/响应/槽输出SHA后计算固定门槛；未运行槽始终保留，零指控不计100%精确率。通过也仅为开发候选，不能代替独立质量、独立性能、生产开放或T039准备。

真实独立目录计划 `/tmp/edumind-p15-full-diagnostic-r04`、真实独立PG计划 `edumind_catalog_p15_t020_diagnostic_r04`（127.0.0.1:15437）。本轮只创建了不同的offline测试库，真实目录/库未创建；新批准前所有执行入口在凭据/输出/PG/DNS前拒绝。

## 验证

85项不同测试通过、0skip（83离线＋2实际隔离PG/HTTPX Mock），详情见validation.json。离线测试覆盖probe完整Schema及已知差异、探针不泄露gold、非严重错误可真实入账后停、假human/漏来源/假误报拒绝、固定小分母与未运行/零指控拒绝。实际隔离PG/HTTPX Mock覆盖两个场景生成＋low审核、负例只澄清而不发场景及原生产拒绝。

所有新代码位于独立isolated_diagnostics/CLI/测试，不改生产Prompt、原Schema、清洗实现、旧冻结文件。原T059的103项验证为既有源码基线证据，不冒充本次真实诊断结果。

负例夹具曾误用中文reason和unsupported_scope，原严格Schema正确拒绝；核对原枚举out_of_scope后修正夹具，两项PG测试通过，没有改Schema或断言。专用PG容器已恢复exited，执行器原样归档run_pg_offline.py。

## 已知限制

合成开发材料已暴露，不能用于T040独立验收。助手逐条复核不能声称独立人类真值；事实穷尽性依实际复核记录与明确来源，执行器只能机械核对覆盖和引用，不宣称自动证明语义正确。概念题自然语言答案及精确匹配的适用性必须逐题检查，不能因为参考答案数值正确就自动认定评分键可靠。

旧失败和所有未运行保持。新包即使执行也可能因质量阈值失败停止；只有实测全部门槛通过才完成T038。下一步须先获得本manifest的A—C/准确外发/新窗口/请求预算和费用例外批准。
