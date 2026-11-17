# T090：R0单次机械通过，待独立语义复核

**仅发送1次DeepSeek官方HTTP，返回200。原严格协议/JSON/完整Schema/局部规则与限定改动范围检查通过，唯一改动为`/paragraphs/0/text`。网络阶段已结束，状态仍为`pending_independent_semantic_review`，没有登记修复或诊断成功。** 无重试、补样、回退或旧批重启。

准备提交`b8019b64f762414cae077afea2541d7175b35e08`；[200文件准确manifest](../manifest.json) SHA256 `78f02e8b065c95537bdd361249e34715d68f070587f177a7914306bbe2b3f4c0`。用户“批准”明确答复上一条准确单次包/新120秒/本批未核实费用与上游限额风险问题，[批准与窗口登记](../execution-approval.json)保留原答复和问题范围。没有继承T088费用例外或未用额度。

本次窗口2026-10-29T15:09:32.736554+08:00–15:11:32.736554+08:00，终止于15:09:40.528622+08:00；控制器单调运行约3.361秒。`--run`和`--check-results`均exit3，表示“网络采集完成，语义仍待复核”，不是exit0修复成功。

## 模型实际改写

原文：

> p 接旧 head，调用者接回 p。

模型返回的完整新段落：

> 先把新结点 p 的 next 指向旧的 head，这样新结点就接在了旧链前面。函数返回 p 后，调用者再用 caller_head 接住这个返回值；局部变量 head 和 caller_head 是两个不同的指针，不要混用。

这段文字是模型输出原文，尚未经独立语义核定。完整候选中的代码、问题、参考答案、节点/状态/动作及顺序均逐值未改；程序没有补填或改写答案。[前后差异与准确意见](before-after.json)保留唯一JSON Pointer及原/新摘要。两句要求是否充分满足、指针措辞是否准确且不引入误解，仍由独立评估者判断，不能由范围合格或关键词命中代签。

## 观察与全量证据

DeepSeek `deepseek-flash` / Responses / reasoning none，外层completed，error/incomplete_details均null，message phase=final_answer；准确Schema回显存在。完整输出是合法候选JSON，2216字符/2640字节，SHA256 `72939c2163abfff5aa2723f82bf05caa421f09492b690fe9aef0a56894a55b5b`，并未返回Schema或非法尾部。

- [完整输出原文](R0-output.txt)、[完整候选的可读派生视图](R0-candidate.json)：原输出文本逐字节保留；派生JSON明确标记为非原始信封、非语义批准。
- [只读汇总](assessment.json)、[响应观察与用量](response-observations.json)：1 real/1响应/1 validated，`repair_success=false`、`diagnostic_success=false`、`full_role_admission_complete=false`、`semantic_evaluated=false`。
- [全部12份私有原件清单](evidence-manifest.json)：准确请求、HTTP状态、完整原响应、grant、summary及7事件的路径/字节/权限/哈希。原件位于`/private/tmp/edumind-p15-r0-once-r01`，0700/0600；原响应未裁剪，Key/Authorization未落盘，传输ID随原始信封保留私有。
- [只读及防重启验证](readonly-verification.json)、[结果manifest](result-manifest.json)、[验证记录](verification.txt)。完整原件/事件/请求/来源/窗口/摘要重算通过；在禁止Key/DNS/socket的陷阱下再次只调用前置门禁，已有目录被拒绝，12原件哈希不变，没有再次调用Provider。
- [独立语义复核交接](semantic-review-handoff.md)：当前没有独立复核结论，也没有设置语义成功的入口。

批准上限保持1HTTP/120秒、单HTTP60秒/DNS9秒、输入占额8192/总输出请求上限4096、请求/响应65536/262144字节。全部请求额度已使用，网络终态不可重启，剩余时间不自动产生新额度。

响应自报输入2964、输出784、合计3748，缓存与推理token均0；仅为Provider报告，不是账单或上游硬限认证。实际账户费用/币种未知，本批费用风险已获明确接受；不继承或授予后续费用例外。

## 结论边界与复现

本次只说明这个R0准确请求返回了机械合格、确有受限改写的候选。它不推翻T088 W4的失败，也不证明修复稳定率、独立生成能力、B/C可比收益或全部角色兼容；整套接口与课程实验门禁没有因此解除。T038 blocked、catalog_only、H封存及正式教学验收标准保持。

```sh
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_r0_once.py --check-results
PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-r0-once-r01/results/check_evidence.py
```

前者预期exit3待语义复核，后者exit0仅表示证据核对通过。两者只读、不读Key或出站，需保留本机私有原件。T090只完成获准单次采集/证据交接，提交后停止，等待独立评估。
