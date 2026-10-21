# 审核配置对照提案 r01（v4.4 固定）

选择 `deepseek-flash`，基线 `reasoning.effort=none`，唯一候选 `low`。输入契约、审核 Prompt、JSON Schema、温度字段0、2048总输出token、60秒截止、无工具/重试/回退保持。不开其他模型，不改生产默认，不修改r05及此前运行的回答、标签、halt或预算。本提案不是 v4.5。

官方资料声明 Responses 支持 low 和 JSON Schema，尚未实测这一组合。思考模式会忽略温度字段，这是切换思考的固有语义，不能把“temperature=0”视作两臂同样确定。别名不固定模型权重，前后调用可能存在服务端非确定性。

## 固定材料及判据

| 材料 | 来源 | 两臂共同判据 |
| --- | --- | --- |
| trace-complete | r05原材料及原实际请求 | pass；无finding/未决/未检查或附带误报 |
| trace-distributed | r05原材料及原实际请求 | pass；跨资源可见支持有效，无需讲解重复全部内容 |
| plan-only-gap | r05原材料及原实际请求 | needs_human；具体指出状态/退出教学缺口，不编造fact等finding |
| assessment-gap | r05原材料及原实际请求 | needs_human；具体指出过程测量缺失，不编造fact等finding |
| fact-contradiction | r03原学生内容与原绑定请求，按v4.4契约重建审核输入 | 具体检出声明18与实际16的矛盾，保持原严重错误拒绝判据 |
| reachable-safety | r03原学生内容与原绑定请求，按v4.4契约重建审核输入 | 具体检出长度3却访问a[4]的可达安全问题，reject |
| gap-and-safety | 新派生：r05过程缺失材料，仅代码source换成r03可达越界代码 | 具体检出a[4]及安全影响并保留严重拒绝；同时审查教学缺口，不能全部降待人工 |

原四组学生内容、计划及其实际wire原文保持；后两份历史内容只为当前v4.4输入契约重绑定身份和政策，原始请求由历史输入快照实现及input_digest校验取得，不能由计划goal倒推。混合例明确标作新派生，不冒充历史冻结样本或独立真值。

每组的两臂使用完全相同的材料、锚点、目标、请求input与结果schema；wire只改reasoning.effort。r05第三条完整实际回答另外绑定为离线回归，不把它当本轮新的基线调用，也不作为模型输入或示范答案。

## 执行、停止和核对

预登记顺序为表格顺序，每组先candidate再baseline，串行最多14次。第一条candidate完整正例使用真实审核请求，先确认结构、锚点及五检查ID，再核对质量；同一次兼容探测也计入14次，不增加隐藏调用。仅官方声明与Mock检查不等于真实兼容。首条不兼容/超时/输出截断即停止，不临时改schema、输出上限或补发。2048包含思考和可见输出，可能不足，失败必须如实记录。

每次只允许一条，返回完整实际材料、意见、用量及准确收据，人工确认后再继续。候选任一自动判据失败立即持久停止；人工发现候选具体证据不成立也停止，不签continue。基线语义失败作为对照观测保存，不冒充通过；只有用户核对该失败后明确继续才能下一条。结构/协议/安全/用量异常两臂都立即停止。无自动重试、修正、fallback、并发、清halt或旧预算转移。

机器只能检查路由、结构、必要类别等信号；不能仅凭类别出现宣称具体矛盾已检出。人工逐项确认实际命题、反例、影响、位置、覆盖缺口及无额外误报。混合例严重错误必须有据，不能用假的severe满足断言；也不能把全部finding清空。labels-human只签样本与判据，真实结果另签准确收据，不预填。

每臂每例仅一次，固定候选顺序有顺序效应；这是小诊断，不是统计证明、独立留出集或正式T040验收。候选全七例正确才有继续讨论更广诊断的依据，不能因此修改生产默认或自动启动正式T040/T041。

## 预算与权限

`proposal.json`逐槽保存实际wire字节和准确保守预留：输入上界为1048576加wire字节的冗余，输出2048（含思考）。按高峰未缓存输入2元/百万token、输出8元/百万token计算，14次总输出不超过28672tokens；字节不是token估算，整窗预留不是预计账单。

本包14次准确保守预留上限为 **30.768502元**，不是预计消耗或账单。当日价格及总输出契约需执行前再核。应用预留不是Provider账户硬限额。当前requests_authorized=0、fees_authorized=0，无run-approval/labels-human，无新真实目录或账本。新准确预算和材料绑定获批后才可登记批准，首先只发候选完整正例；不沿用r05费用批准。

官方来源：[价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)、[Responses参数与总输出上限](https://api-docs.deepseek.com/api/create-response/)、[思考模式及温度语义](https://api-docs.deepseek.com/guides/thinking_mode/)。2026-10-16价格直接读取，Responses直读超时后由官方索引全文及思考文档核对；执行当日不可验证则停止。

离线准备：`backend/.venv/bin/python scripts/prepare_review_config_comparison.py --write`。真实入口：`backend/.venv/bin/python scripts/run_review_config_comparison.py --run-one`；缺任一批准先拒绝，不读key、不DNS、不新建真实目录。准备器禁止覆盖不同的既有冻结包。
