# d01：用户明确要求新Key直接生成一次

用户在上一轮计数404停止后再次明确“换了 Key，直接调用一次”。此次指令只授权当前.env的一次直接生成，明确跳过计数；使用此前已展示和批准过的原S1固定OK请求参数（549字节，输出16），不是重启旧批次。新manifest为执行前追溯冻结，**未经用户再次逐哈希独立审阅**，授权登记如实标记false，不伪造新准确包审批或独立人工评审。

端点固定 https://www.cbbb.fun/v1/responses，gpt-6-luna/Responses/none/default/store=false/stream=false/strict:true，无工具。凭据只从当前项目.env的EDUMIND_PROVIDER_API_KEY提取，不向官方发送、不记录或输出值；新Key来自用户陈述，不宣称已确认不同上游厂商。

最多1 HTTP/1生成，0计数，唯一新批次p15-direct-relay-once-d01；请求max_output_tokens=16，输入本地占额4096，本地USD0.01规划占额，预约起40秒/应用39秒/DNS5秒/HTTP29秒，响应≤2MiB。实际币种/费率/上游硬限仍未知，客户端限制不保证上游费用封顶；延续用户已获告知的同一中转未知费用背景，未虚构新供应报价或可靠成本。无论返回何种结果均保留本地全占额，不称发票或可信实际结算。

这是用户主动要求的一次直生成观察，不修改先前失败记录或教学链路，也不一般性关闭计数门禁。记录HTTP、固定OK/Schema、instructions、输出上限与reported usage；**count_equivalence_tested=false**，不能用reported input代替独立计数证明一致。HTTP200或固定OK不代表完整兼容/质量通过，T038不能因此done，课程不解锁。任何结果均终止此批次，不能重试/改路由/补样本或恢复旧批次。

执行前离线：`backend/.venv/bin/python -m pytest scripts/tests/test_p15_direct_relay_once.py -q`，7 passed/0skip。执行命令只允许一次 `backend/.venv/bin/python scripts/run_p15_direct_relay_once.py --execute`。--check不读.env或发请求；独占输出 /tmp/edumind-p15-direct-relay-once-d01 禁止重启。
