# ADR-0044：最小 Schema 实验的最终回答阶段元数据兼容

2026-10-28；Proposed。仅T076 / schema probe-p02；T075为离线准备，不授真实请求。p01的T074已完成采集、结论不确定并终止。

## A：准确已知字段及原件隔离

在DeepSeek生成响应的单个assistant message上，仅新增认可`phase: "final_answer"`；缺省phase沿原规则，显式null、commentary、其他值/位置或类型仍拒绝。status=completed、role=assistant和原消息/内容允许字段保持，其他未知字段、工具、reasoning、Schema、来源/用量/输出界限均继续按原严格校验。

[OpenAI官方字段说明](https://developers.openai.com/api/docs/guides/deployment-checklist)将该值用于最终回答；DeepSeek本次原件另独立证明它实际返回这个值。文档不能证明DeepSeek完整上下文/版本/账单，phase也不作为身份、教学或审核通过凭据。

原始响应先按字节保留。只有私有校验视图移出这个准确字段，其他部分原样送原generation validator，额外记录envelope_policy=synthetic-final-phase-v1、实际phase及identity_verified=false。该视图不作为续写历史；原件保留phase，以免丢失后续消息阶段语义。不修改旧wire模块、生产网关、p01源码/manifest/原件/失败结论或独立样本。

## B：独立p02与最小预算

新准确S1/S2字节与p01完全相同，唯一对照仍为kind.type：DeepSeek官方`https://api.deepseek.com/responses` / deepseek-flash / none / temperature0.2 / strict true / stream-store false / max_output_tokens32。两者均使用A的新有界响应规则，S1不完整通过不发S2，S2任何结果均终止。

只用专用EDUMIND_DEEPSEEK_COMPAT_API_KEY；新目录`/private/tmp/edumind-p15-schema-probe-p02`一次性创建，不恢复或续用p01的未用1请求。新登记窗口90秒、最多2HTTP、单HTTP25秒、DNS等待9秒/固定无凭据子进程、同核定公网IP；请求/响应1024/65536字节，输入/输出本地占额8192/64。没有重试、重定向、回退、未知重发、计数或额外探针。

与p01相同的公开费率快照/占额参考$0.0025344仅是参考，实际账户币种/费率/账单及上游输入/输出硬界未独立验证；提议本批再次明确接受实际金额不设硬上限及取消后可能计费。旧p01批准、费用例外和剩余额度均不继承，必须准确p02另批。

## C：结论、重放及课程门禁

已捕获p01的S1在新规则下可离线解析95输入/6输出且Schema/内容符合，旧规则仍报WIRE_MESSAGE。此事实只是反事实校验重放，不回填p01 control、不结算旧unknown，也不能据此补发旧S2。新旧版本用不同文件保留历史可核验性。

新p02的S1有效且S2匹配原Schema缺discriminator 400，仅支持最小enum-only形式被拒绝；双成功说明该窄拒绝没有复现；其他情况均不确定并停止。不得把这一对照变成原完整Schema唯一根因证明。

相关C规划/内容及审核准确wire Schema仍须准入后才准备一份新的可评课程，保留完整本地Schema和教学标准。此包没有课程、学生、e03真值或sol外发，不启动课程/完整诊断、评分、生产或部署；T038 blocked、catalog_only、H封存保持。
