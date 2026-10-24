# ADR-0031：当前.env中转原故障单次复测（待批准提案）

日期2026-10-24。T057只准备入口与准确材料；用户已选择当前.env新供应并要求失败弃用，但未见此准确包的费用/未知上游风险批准。不继承p01无限例外或官方r01批准，不修改任何旧冻结文件/教学链路。

## A：准确供应和原故障复查

.env当前公开Base URL是 `https://www.cbbb.fun`，模型 `gpt-6-luna`，structured transport `responses_json_schema`。本次显式映射到 `https://www.cbbb.fun/v1`，只 POST `/v1/responses/input_tokens` 与 `/v1/responses`，不改.env。该映射是待批准的包配置，不声称已获供应商文档证实。凭据只从项目.env的 `EDUMIND_PROVIDER_API_KEY` 在双批准通过后提取，不继承进程旧变量、不发往官方；模型等身份变化即拒绝。

请求复用原p01/S1准确549字节，SHA `cc45e19ba242760b756bca579ee80e45c6dd93e35c351ed6128a8bef7e459422`。Responses/none/default/store=false/stream=false/strict:true，两个system加固定OK，完整Schema不变。只发送相同字节的计数一次、生成一次，复查count vs usage、额外instructions、输出上限回显及固定OK/strict Schema。S1 instructions合法null可接受，非null须与准确system列表或双换行连接一致；max_output_tokens=null为证据未决而停，不把null直接判为服务端一定忽略上限。

这不能声称新key换了上游厂商，也不重发r02非法allOf Schema或课程内容。新key的后端路由/版本未独立证实；只观察当前凭据的准确配置。

## B：准确极小探索预算及未知费用

新批次 `p15-relay-regression-r01`，最多2 HTTP/1生成。输入本地占额4096，请求max_output_tokens=16（含推理），计数必须1..4096才发送生成。预约起90秒，应用89秒，DNS独立无凭据子进程5秒，单计数10秒/生成30秒，每响应≤2MiB；无重试、重定向、自动改路由、备用模型、补样本或重启。

用户明确没有该新供应价格资料：**实际费率、计数收费、币种均未知**。不套用OpenAI报价。提案本地规划额USD $0.01（10,000 micros），单对最大占额$0.008208，其中计数留额$0.004096、输入/输出按假设$1/百万token留额。这只是本地规划记账，未知供应费率下不能称保守覆盖实际费用；不是供应商报价、发票限额或金额上界证明。正常返回的local_accounting同样不是发票，实际收费与币种保持null。

本次是独立的一次探索例外，实际token/费用可能越过本地占额，中转可能忽略参数或在客户端超时后继续计费。用户必须准确接受**币种与费率未知、无法保证实际账单封顶及上游硬界未验**，才能发送；不沿用旧“无上限”。若要求可靠账单上限，则先取得供应商资料，本包不能保证。本地总规划额仍有限，不能随意追加。

## C：失败即弃用，成功也不自动扩大

任一HTTP/Schema/计数/指令/上限/身份/凭据回显/存证/时钟/预算问题即停，unknown保留，不补请求。该配置判 `candidate_rejected_stop_using`，按用户要求停止使用这项供应，不继续调Prompt、改断言或复试。原始私有证据只留保护目录，后续只发布去敏结果。

单例干净仅为 `original_fault_not_observed_one_case_only`，不等于完整兼容矩阵通过、不能完成T038或直接准备/执行课程诊断；若需补S2必须另冻准确包批准。每个结果均终止本批次，输出目录独占，不能恢复。旧p01/r03、unknown96k/16016和课程教学门槛/H封存保持。
