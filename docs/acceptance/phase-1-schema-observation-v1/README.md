# Schema失败位置诊断（零调用实现）

用于后续独立冻结包。原suite-r01首条失败依然只有additionalProperties类别，没有正文，不能事后恢复具体字段、verdict或语义结论。原包、旧执行器、生产适配器与规则均不修改；本目录不是新真实运行包，没有新增预算或真实调用批准。

新增`schema_failure_observation.py`，在原安全元数据上增加`schema_location`。仅STRUCTURED_SCHEMA_MISMATCH且响应完整、completed、单助手消息/单文本块时，使用已预留的精确请求中的原Schema，在内存中按同一适配器文本选择与JSON解析规则重现首个Schema违规；不是放宽校验、删除字段或修复响应。外部Schema引用拒绝，不读文件/联网解析；请求、响应受原字节限制。诊断只定位首个违规，不声称找齐其他问题或完成语义审核。

记录：原request wire摘要、Schema摘要、规则关键词、实例路径、Schema路径。路径限32段，数组索引限0至100000；字段/Schema片段来自静态白名单，其余显示<redacted>。additionalProperties=false且无patternProperties时计算额外字段；required计算缺字段，最多16个，记录总数/截断标志。白名单字段名可见，其余只保留字段名SHA256；即使是短ASCII未知键也不直接输出。任意字段值、错误message/instance、学生正文、模型思考、原响应、Key和请求头不落盘。

缺响应、部分响应、解析或诊断失败只记录明确不可用枚举；不填造字段位置，不推断模型verdict。schema_location只作故障定位，不产生通过或继续授权；原错误、用量计费、先持久halt再写诊断以及人工具体证据门禁保持。

未来独立入口`run_review_suite_observed.py`使用尚未准备的suite-r02路径。它与r01执行器的差异只有独立路径/run_id、诊断模块和传入reserved wire；输入、Prompt、Schema、模型、low、8192、60秒、判据均未改。无run-approval时在Key/DNS/真实目录前拒绝。未准备r02提案/材料/标签/预算/授权，不能直接发送或沿用r01剩余额度；旧r01仍halt。

验证：真实适配器路径的httpx MockTransport，不是云端调用。13项新增覆盖根/嵌套额外字段、未知键/字段值隐私、required/enum/type、数组索引、多字段截断、部分/缺响应、外部引用、不匹配重验、缺授权、诊断写盘失败后不能重试。连同旧回归254项通过，具体命令见validation.json。

API依据：[jsonschema错误路径说明](https://python-jsonschema.readthedocs.io/en/v4.18.3/errors/)。使用absolute_path和absolute_schema_path，不序列化message或instance。

本次只改善后续失败的可定位性，不证明模型已解决plan-only-gap，不改变T040 blocked或catalog_only。下一步如需真实复验，须另行冻结小包与准确预算，不在本次执行。
