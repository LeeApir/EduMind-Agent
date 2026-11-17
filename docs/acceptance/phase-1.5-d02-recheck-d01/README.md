# D02 两场景回归 d01：准确执行准备包

状态：仅准备，execution-approval.json 的 approved=false。真实调用0；旧r05与单次sol结果保持，T038继续blocked。本包不等于完整诊断，不自动继续其他课程或独立验收。

仅重新生成原 `D02-known` 一份合成课程：原目标“学习单链表头插，用C代码和练习组织2个场景。”和原画像自述逐字段保留；重新规划且必须恰好2场景，必要上游使用此次实际生成内容，不使用旧错误正文提示模型。无真实学生、旧签核课程、封存H或其他33槽。

生成仍为 https://api.deepseek.com/responses / deepseek-flash / reasoning none，规划free-course-plan-v1、场景free-scene-generation-v4、原完整Schema；本地机械准入free-scene-hard-gate-v3及私有free-scene-consistency-v1。审核仍为 https://aiapi.world/v1/responses / gpt-6.1-sol / low，development-scene-review-v2及原Schema与isolated-review-observability-v1。准确路由、版本及Schema摘要见plan.json；不保证远端模型别名对应的底层快照不变。

本地一致性报告作为独立私有证据保存，不加入sol请求或改变审核Prompt。审核仍发送原目标、课程计划、正文、私有答案、动作、必要上游。助手先实际读课再看sol意见；逐块事实、逐题答案、可接受/拒绝输入及画像自述全部核对，同时逐条裁决一致性建议、承认未覆盖范围，不能把未发现冲突当作语义正确。reviewer=Codex assistant / delegated_assistant / independent_human_truth=false，不让用户填材料或冒充独立人工真值。

拟新独立预算：最多15 HTTP＝13生成＋2场景审核，通常5次（1规划＋2生成＋2审核）。13生成包含原有限结构修复，不含语义重生成。新登记起1800秒（30分钟，含助手复核），生成课程600秒、每请求120秒且不晚于绝对截止。无计数探测、传输重试、回退、重定向、未知重发、补样本、自动新批或旧批次重启。旧相关实验累计25请求/报告120900输入/26000总输出原样保留；若用完本包累计最多40请求，非全项目累计。

待本包独立批准的例外：token与金额不限。当前实际费率、币种与服务硬限未知，不套用其他供应商价格、不继承旧费用例外。每请求max_output_tokens≤8000只是请求参数，服务可能忽略或在客户端取消后继续计费；中转完整上游上下文与留存不可独立证明。store=false及回显不是隐私政策或指令送达证明。

生成使用独立DeepSeek Key；审核优先独立AIAPI Key，仅通用Base URL准确等于https://aiapi.world/v1时才允许通用Key，两者必须不同。沿用公共IP/Host/SNI绑定及准确来源检查。密钥不入Git、输出或日志。记录完整请求/响应于私有输出，推理摘要只核对形状/大小，不解释或转发。

协议、来源、安全、未知发送、请求或时间边界异常立即停止，保留失败和unknown。sol非pass先暂停由助手复核：确认问题或无法判断则失败停止；只有有源证据的误报裁决可继续尚未审核的场景，绝不重新生成已有课。新一致性发现仅为待复核，未裁决不得完成报告；真实发现同样不能隐藏。原首次Schema/事实/答案/零自然严重错误标准不降低；本包局部结论更保守要求实际观测的首次Schema全部通过、完整课程与逐项复核通过。未运行/未知不剔除、不伪造分母。

工程入口（均在仓库根目录）：

- `backend/.venv/bin/python scripts/run_p15_d02_recheck_d01.py --check`：纯离线核对manifest与配置，不读Key/DNS/PG或创建输出。
- 准确批准后才可 `--step`：单课程生成及顺序场景审核，非pass停在检查点。
- `--review <报告路径>`、`--adjudicate <误报路径>`：本地实际复核导入，不发送请求或自动继续。
- `--assessment`：只读核对准确批准、原始字节与协议观察，输出局部结论；T038_completed、independent_validation_passed、production_admitted始终false。单画像不提供个性化对照结论。

独立输出 `/tmp/edumind-p15-d02-recheck-d01`；独立库 `edumind_catalog_p15_t020_d02_d01`，仅专用PG的127.0.0.1:15437。准备阶段不创建这两个真实路径。未获准入口在Key、数据库、输出及网络前拒绝；新1800秒窗口须明确登记，不能通过重跑续期。批准必须绑定本manifest摘要、准确服务/合成外发、请求/窗口与费用例外；不把“好，开始”登记为新费用例外。

隔离调度器和slot为旧r05的明确窄范围副本，变更为15预算及仅D02，生产调度器和旧包字节不动；传输、原审核/逐题标准、原始证据复验复用原严格实现。验证结果及实际命令见validation.json及run_pg_offline.py；Mock仅验证工程接线。旧冻结包在当前源码不匹配时保持原件，不修改旧SHA。不push、merge、部署或推进T039。
