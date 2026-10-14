# DeepSeek 独立接入复验：通过

用户先指定切换自有DeepSeek，再明确“用deepseek跑一遍”。本轮只执行4项公开接入探测，防护上限4次/CNY0.10、128总输出/关闭思考、15秒、0重试/回退/工具执行；不转授Qwen预算和成绩，不包含T040/T041。实际参数、源码、官方峰值未命中价格与授权依据分别冻结在本目录，数值防护上限由执行器设定，未伪称用户逐字提供该数值。

冻结源码909ddb6后真实执行4次全部HTTP200：文本0.501559s/9+1tokens；严格json_schema 0.845954s/59+5tokens；auto工具0.837192s/282+38tokens，单个emit_probe参数ok为true；语义流式0.846648s/9+1tokens，response.completed及实际usage读取通过。全部返回deepseek-flash且正常完成，未把Chat的[DONE]规则套用Responses。

[独立结果](results/r01.json) 核对177项冻结文件SHA/全部wire SHA/SQLite持久预留与结果一致。实际359输入+45输出=404tokens，usage无未知；保守预留CNY0.014534、按峰值未命中单价计算的已知token参考额CNY0.001078，均非实际账单；可能有非高峰或缓存抵扣，不据此声称免费。106离线测试/Ruff通过；密钥只从ignored .env进入内存/发送头，不进证据或Git，目标DNS全部公网检查、固定IP/Host/SNI、TLS验证、禁代理/重定向保持，正式响应不持久保存正文。

本次证明当前服务端系统模型DeepSeekResponses工厂路径的公开协议能力，不证明另一条P1 BYOK Chat路径、教学质量/审核可靠性或端到端P95。T040必须重新冻结实际消费路径和正式生成/审核预算，不能把接入成绩冒充质量通过；模型DeepSeek-V4.1-Flash来源于官方当前模型映射，后台构建revision未知。四类其他真实接入仍延期。已完成Qwen T039不重开、不改分；本次独立证据作为后续选定DeepSeek的前置。T040/T041未启动，没有动态开放。
