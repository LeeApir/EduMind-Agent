# 独立最小确认方案（准备方向，非真实授权）

离线能确定准确形态和标准等价性，不能证明远端实现行为。若要验证“本端点是否要求enum显式type”这一窄假设，建议全新两请求合成对照，旧p01、e03和独立真值不参与。

1. S1正控制：根object只含kind；kind为`type:string`、原动作3值enum；required kind、additionalProperties false。固定合成消息要求输出`{"kind":"show_state"}`。
2. 仅S1取得完整可信响应、准确JSON和有效用量后，S2复制同一请求，**唯一差异为删除kind.type**。S2为末次观察，任何结果均终止本批。

两者同DeepSeek官方`https://api.deepseek.com/responses` / deepseek-flash / none / temperature0.2、strict true、stream/store false；无tools、私有课程或参考答案。拟最多2HTTP、每次max_output_tokens32，新独立短窗口，禁止重试/重定向/回退/续批。实际token与金额门禁、凭据、时钟、响应限制及准确源码还须在独立包中冻结并获批，不能继承旧90请求或费用例外。

预注册解释：

| 观察 | 可得结论 |
| --- | --- |
| S1失败 | 对照不成立，S2不发，不能归因enum-only。 |
| S1通过，S2返回匹配的Schema缺discriminator 400 | 支持这个最小enum-only形式被该端点拒绝；仍不能定位原完整Schema的服务端首个/唯一失败点。 |
| S1、S2都取得有效输出 | 该最小形式的拒绝未复现；不能继续把原错误归因enum-only。 |
| S2其他错误、超时、来源/用量异常 | 结论不确定，保留unknown，停止。 |

不自动加入第三个请求、不发送原全Schema作补测。即使得到支持enum假设的观察，也只是语法兼容证据，不宣告C规划/内容或AIAPI审核接口已通过。后续具体适配、相关角色兼容准入及一份课程的准确可行性包均应独立准备，保持完整本地Schema和原教学标准。
