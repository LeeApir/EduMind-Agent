# 规划补丁后的 D02 正式调用测试 d03（待批准）

用户明确要求先完成规划补丁，再做一次正式调用测试，之后再重评，并确认修复范围。T065已独立提交fc5cfc6，181项离线/隔离PG-Mock通过。本包是真实HTTP端到端诊断准备，**不是生产开放或正式课程签核**；当前批准false、新真实0。

## 准确版本与范围

只有原D02-known合成目标“学习单链表头插，用C代码和练习组织2个场景。”及原画像自述，slots.json原字节保留。本批全新规划/生成，必须恰好两场景；旧错误正文和助手判定不作为修课提示发送。配置为：

- DeepSeek官方 `https://api.deepseek.com/responses` / `deepseek-flash` / none，规划 `free-course-plan-v2` 和 `planning-objectives-and-constraints-v1`，场景 `free-scene-generation-v5`。
- 准入事实 `free-scene-hard-gate-v4`、私有一致性 `free-scene-consistency-v2`。目标/来源/覆盖验证器及输出Schema字节未改，无服务端自动补引用或自动删学习目标。
- AIAPI `https://aiapi.world/v1/responses` / `gpt-6.1-sol` / low，原 `development-scene-review-v2` Prompt/Schema。
- ADR0040 A—B的两个匹配规范UUID元数据隔离策略原样复用，需要本包明确延伸适用范围；不新增或放宽任何字段，不把UUID、回显或token数量当指令/身份/完整上下文证明。摘要/明文/密文及全部来源/协议门禁保持，原始字节与SHA保留，最终只读assessment重验。

## 新窗口与停止规则

拟新登记起 **1800秒（30分钟，含助手复核），最多5 HTTP＝1规划＋2场景生成＋2审核**；单请求120秒、课程生成600秒，均不晚于总截止。首次Schema/本地规划校验失败即停，没有结构/语义修复、传输重试、重定向、回退、未知重发、补样或自动新批。若质量/协议异常，保存完整失败和未运行项；本次测试结束后再按真实证据重评，不自动追加补丁。

旧相关30请求/报告138390输入、31075总输出保持；新最多累计35请求，非全项目历史。拟本包token/金额不限须重新明确接受：实际费率、币种、服务硬限和中转完整上下文/留存未知；max_output_tokens≤8000只是请求参数，客户端取消后可能继续计费。不继承旧停止批次的剩余额度、窗口或费用例外。

仅向两个指定服务发送本批合成目标、画像自述、计划、正文、私有参考答案、动作及必要上游，不含真实学生、旧签核课程或封存H。生成使用专用DeepSeek Key，审核优先独立AIAPI Key，只有通用Base URL准确为https://aiapi.world/v1才允许通用Key；两Key必须不同，不进入Git/日志/输出/前端。

## 实际复核与结论边界

由我先读课程再看sol意见，逐块核对事实、逐题核对状态/参考键/允许和拒绝输入，核对原目标、画像自述及所有本地一致性建议。reviewer=Codex assistant / delegated_assistant / independent_human_truth=false；没有假人工标签。sol非pass先暂停核对，只有准确来源的误报裁决可继续余下审核；真错误或未解决质量疑问停止。模型pass不等于可靠答案。局部通过要求三个首次响应都通过、两场景完整且逐项实际复核通过；原教学阈值不降低。

这一次局部正式测试不补全T038原34槽分母，不宣称独立留出/性能或生产验收通过；单画像不提供个性化对照结论。旧d02结果和REASSESSMENT是历史记录，本轮遵从用户最新“先补丁、正式测试后重评”的执行顺序，不实施模板/IR新方案。

## 入口与隔离

根目录 `backend/.venv/bin/python scripts/run_p15_d02_formal_d03.py --check`只核对冻结SHA，不读取Key/PG/DNS或创建输出。`--step`必须准确批准新包、规划v2范围、ADR0040 A—B本批适用、外发/5请求/新窗口及费用例外；否则提前退出2。`--review <报告>`、`--adjudicate <误报裁决>`仅本地导入，不自动继续；`--assessment`只读复验原始证据及局部结果，T038_completed始终false。

独立输出 `/tmp/edumind-p15-d02-formal-d03`，独立库 `edumind_catalog_p15_t020_d02_d03`（专用127.0.0.1:15437）；准备阶段不创建这两个真实路径。复用d02的严格隔离传输/调度/来源及复核实现，新增薄层只绑定新批次和旧用量；不是重启旧d02。

验证命令及实际结果见validation.json，run_pg_offline.py使用随机独立测试库与HTTPX Mock。准备通过不代表模型真实遵守规划v2。准确批准须绑定manifest SHA，批准登记不列入manifest以免循环。无push、merge、部署或自动推进T039。
