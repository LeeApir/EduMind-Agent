# 失败诊断留存修复（零调用）

本次交付安全诊断模块与独立后续执行器，真实Provider请求0。原配置对照r01、r05和此前运行的材料、源码、结果、预算与halt不变。r01第三次尝试缺失的实际发送数、细分原因及用量仍为未知，不能事后补造。

## 实现与边界

`scripts/acceptance_support/failure_observation.py`输出`safe-failure-observation-v1`，只保留以下允许字段：

| 类别 | 留存内容 | 限制 |
| --- | --- | --- |
| 失败位置及类型 | 固定执行阶段、归一化错误码、ProviderError细分枚举、JSON语法枚举、允许的schema关键词 | 不保存异常消息、repr、堆栈、schema路径或生成值 |
| 发送状态 | 交给HTTP传输层的次数、已观察到的HTTP状态 | dispatch不证明服务端收到；未知保持null，创建传输之前的凭据阶段可以确认0 |
| 响应摘要 | 已捕获编码body的字节数/SHA256、流是否完整结束、可完整解码时的响应摘要 | 部分捕获不能冒充完整响应摘要；不保存响应正文、请求头、URL参数、思考或学生文本 |
| 响应状态 | 允许的completed/incomplete/failed等状态和max_output_tokens/content_filter原因 | 只解析完整有界响应对象，任意字符串/对象不会转存 |
| 用量 | 输入/总输出计数及来源，非法计数标记 | 依次取已返回result、ProviderError附带usage、完整可解析envelope中的usage；每字段独立，未知不填0，不从文本长度推算；总输出包含思考 |

用量是Provider观察值，来源可核对，不代表独立账单验证。布尔、负数或超出安全数值范围的值不作为计数落库；正常范围但超过运行上界的实际计数保留，并由预算内核将失败升级为`USAGE_BOUND_EXCEEDED`。不改变整槽费用预留、不退款或增加调用。

`scripts/run_review_config_observed.py`保留原对照的材料/Prompt/Schema/判据与门禁逻辑，但使用独立`review-config-r02`路径和运行标识。失败时先使用可用计数结束预留并持久halt，再以0600独占写入`<slot>-failure-observation.json`，绑定准确proposal、slot、attempt与预留wire摘要。诊断文件写入失败也不能解除已持久halt或允许重试。文件系统或账本本身不可写仍可能使诊断无法保存；保留不确定预留状态并拒绝继续，不能宣称磁盘故障下必有完整记录。

可明确区分本地候选判据失败与Provider输出失败：前者记录`local_gate_code=CANDIDATE_CRITERION_FAILED`并归一化为`INVALID_OUTPUT`，不误称安全问题；已知用量门禁保持具体失败码。本地路由判据及真实结果不重分类，旧r01账本不更改。

没有改生产适配器、默认模型配置、Review输出Schema、DB/API、旧执行器或冻结包。本次独立JSON仅是私有诊断文件的结构，不替代模型审核结果。

## 验证方式

离线测试通过真实适配器解析路径和Mock HTTP流触发输出上限、结构化JSON/Schema错误、错误响应JSON、429、连接/流中断、未知用量、凭据/DNS前失败、超时/取消、反射密钥和不可信字段。验证流完整性、gzip编码与解码摘要、错误usage传递至预算账本、超过上界停止、诊断写失败不重试，以及正常成功仍只发一次并等待准确收据确认。合成密钥和正文哨兵不得出现在诊断JSON中。

这里没有复原r01第三条真实响应，没有证明候选low的质量有效。`example-safe-failure.json`是明确标记的合成示例，不是实际第三条的证据。

## 后续状态

当前只有后续执行器实现，r02运行包尚未准备或冻结，无新预算、标签批准或真实账本。默认CLI因缺批准/包而在读取Key、DNS及新建真实目录之前拒绝。未来准备器必须同时绑定本新执行器和安全诊断模块及全部实际wire；不能直接复用r01 proposal/approval或把旧14次余额转移。

旧r01继续持久停止。是否开新诊断、使用何种输出上限，应在新的具体运行包及准确预算形成后再决定；本次不提高2048、不重试、不发新真实请求，T040与正式验收保持blocked/catalog_only。
