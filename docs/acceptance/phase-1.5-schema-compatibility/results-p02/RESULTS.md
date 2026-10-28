# T076 p02：最小 enum-only 拒绝已重现

准确批准提交4a52782，manifest `c40aa91a6bbbb6f0c21c7c61d8f66459800826c674ce5080327bf89759718cf4`，登记ADR0044-approval-20261028.json与probe-p02/execution-approval.json。新窗口2026-10-28 20:47:46至20:49:16（Asia/Shanghai），不继承p01额度或例外。

## 对照结果

| 请求 | 唯一变化与实际响应 | 判定 |
| --- | --- | --- |
| S1 | kind带type:string；HTTP200/completed，输出准确`{"kind":"show_state"}`，phase=final_answer；原generation规则＋新有界phase视图完整通过 | 有效正控制，服务报输入95/输出6/总101、推理0。 |
| S2 | 其余原始请求字段相同，仅删除kind.type；HTTP400 invalid_request_error，提示one of type, anyOf, $ref field is required | 与预注册错误匹配，最小enum-only拒绝已观察。无usage，保持unknown。 |

两请求同端点/模型/参数、同次核定公网IP和Host/SNI，body分别581/565字节，源字节与冻结S1/S2完全相同，没有传输重试/重定向/回退/补样。已在S1控制通过后发送S2，S2结束后终止。本批2 real HTTP；此前schema p01另有1次，独立账本不合并为余额。

只读重演确认started→S1预约/目标/发送/观察/控制通过→S2预约/同目标/发送/观察→terminal，全部有效事件位于准确90秒内，摘要/原件/来源及终态匹配。outcome=minimal_enum_rejection_observed、state=terminal、evidence_verified/recorded_window_verified=true。--run和--check-results均exit0；这表示预注册窄观察完成，不是课程或原完整Schema兼容通过。

## 结论边界与修复方向

本次单变量对照支持**DeepSeek该端点在这个最小形式中拒绝不带type的字符串enum**。T072已精确定位原B复杂请求的两处同类形态，故“补明确字符串类型”现在有实际协议证据支持，不再只靠错误字样推测。

标准JSON Schema仍允许enum不带type，因此不能称原Schema标准非法；也不能据本对照定位原复杂请求服务端遇到的首个/唯一失败节点。联合类型、动态对象及其他约束的实际支持仍未证明。单对样本不保证所有服务集群/别名未来行为。

新增phase视图在实际S1完整通过，原响应完整保留；缺instructions回显及上游模型/上下文/账单仍未认证。没有修改p01失败结果、原始响应或教学标准，没有模型课程、学生/e03真值、审核模型或sol调用。

下一步应对相关C规划/内容及审核Schema只做接受集合不变的类型显式化，保持所有原约束并用独立合成协议fixture验证每个实际角色Schema。若其他约束被服务拒绝，记录准确位置/证据并停止，不删约束补过。相关角色协议通过后才准备一份可评课程，不重启完整诊断或把本观察计入T038教学分子。

## 用量、费用与原件

本地占额2请求/输入8192/输出64；S1的95/6仅为接口报告，S2未知协议/用量占额1；没有退款或剩余额度继承。实际费用、币种、账单未知，400不能记成零费用。参考公开费率不补造账单。

原件目录`/private/tmp/edumind-p15-schema-probe-p02`，0700/0600；逐文件SHA见evidence-manifest.json，重算值见assessment.json。原件不提交Git；准确47文件及旧p01原件/源码保持字节一致。没有续写历史或将校验视图发给服务。

T076只完成本次受控观察与证据采集。原复杂Schema的全链准入、课程可行性、教学正确性和正式质量/性能均未获得通过结论；T038 blocked、catalog_only及H封存保持。
