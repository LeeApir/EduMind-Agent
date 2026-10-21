# C/screen-safety：传输超时，最后候选及本批研发已停止

用户确认screen-fact实际发现/全部引用后，screen-safety仅发送尝试1次。执行器返回TIMEOUT，持久写入TECHNICAL_OR_CRITERION_FAILURE和**STOPPED_SCOPE_DISCUSSION_REQUIRED**，next_candidates_allowed=0。没有重试、加时、换配置或后续调用。完整安全审核结论没有返回，不能记作模型安全缺陷漏检、reject、pass或Schema失败。

## 实际技术证据

- 请求已到ExactTransport并取得准确wire/目标授权，sent=1；该标记在inner.handle_async_request之前递增，故不证明HTTP已到Provider。
- 未收到HTTP状态/响应体：http_status=null、raw_bytes=0、raw_complete=false，provider_error/usage均null。空流SHA256仅表示没有收到字节，不是正常空HTTP响应。
- 从本条预约created_epoch到私有receipt文件mtime为**5.531秒**（含本地预检/开销，不是精确Provider计算时间）。配置connect=5秒、read=60秒、整次外层≤60秒；观测接近连接限时，未达60秒整次上限。统一TIMEOUT丢失具体异常阶段，不能唯一判定DNS/TCP/TLS/读响应或上游原因，也不能说模型推理超过60秒。
- 此次Provider是否收到请求、是否计费、输入/输出tokens均未知，不能记为0费用/0tokens。没有模型断言或引用可核对。技术细节见screen-safety-technical-review.json，原安全材料和expected reject不改。

receipt摘要`3f5836b63440d752a3a4d72e52a9fcf0a228febe01426e79b7d09380a8766667`。

## 部分结果保留与退出

本轮消耗7个预约/发送尝试，其中6条收到完整HTTP200并已由用户实际确认：完整Schema兼容、4个过程校准、事实矛盾reject及正确a1/a6引用。第7条安全样本技术超时；后5条（混合缺陷+4旧未参与近期修复材料）没有预约或发送，余槽不可复用。

6条完整响应已报告输入96000、输出2646，共98646tokens；超时条用量未知，**无法得出全轮完整实际Token总量或账单**。六条已完成调用耗时合计53973ms，不包括本次超时，也不是端到端P95。

安全/混合/未参与修复材料未完成，不能用既有正例或事实检出推论严重错误总体召回或正式98%/95%/90%通过。此次结束原因是已批准的技术失败退出规则，**不是已经观察到新候选虚构要求、错误证据或严重漏检**。两类失败分开保留，不将可用性故障伪记语义不合格。

最后唯一Luna/high候选本轮已终止，本批自动审核研发停止。下一步只讨论交付范围：是否保留目录版、收缩/延后动态能力或另定人工签核交付方案；当前不自动实施这些产品变更，不恢复任何旧余额/候选，不以新模型/Prompt/预算延续本批。恢复研发必须先有明确新的范围决策。

正式T040保持blocked，catalog_only及原课程签核安全边界不变。旧low及其他历史失败/标签/未发保留。源码未改，原106离线证据沿用9288782；本次核验484源、实际预约/超时receipt/终态与旧停止，未运行新的业务测试或Provider探测。
