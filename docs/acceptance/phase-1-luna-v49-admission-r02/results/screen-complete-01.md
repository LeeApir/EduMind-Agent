# Luna r02 首槽：Schema传输拒绝，运行已停止

用户批准准确冻结包、12材料/标签与最多12次诊断后，仅发送screen-complete一次。HTTP400，安全解码provider code为invalid_json_schema，JSON错误281字节/原始与解码读取完成；规范映射CAPABILITY_UNAVAILABLE。错误提示某个嵌套Schema必须带type；路径中的部分字段已脱敏，不能确定具体字段，也不能猜测只有一个问题。

没有审核回答、没有Schema通过或语义成绩，未检验正确对照。真实次数1，余11未发；输入/输出tokens、实际费用均未知，不记0。用户单次自测接通不能替代这一完整审核Schema兼容性验证，不据此断言模型本身不可用或审核能力失败。

SQLite持久halt=CAPABILITY_UNAVAILABLE，唯一槽保留reserved记录；这是已知发送失败，不是可重放或返还槽。没有重试、换参数、回退或下一模型请求。既有v4.9、材料、Schema、旧Qwen/DeepSeek结果/额度及生产catalog_only均未改，T040正式质量未启动。

已保留无密钥/无原始错误正文的安全receipt、实际HTTP状态/response摘要和安全词表信息。代码与412来源仍匹配冻结；未修改源码或重跑原87离线回归，沿用60d0e58准备证据。真实HTTP失败和Mock通过分开记录。

后续若继续：先零调用对照完整实际wire中所有Schema的字段/层级/type与该渠道约束，列明证据；不能从脱敏路径猜具体字段。修复必须新执行包/新准确调用授权；当前r02继续停止，不把旧余11次搬到新包。
