# T111 · AIAPI 三次对照复测

按用户指定对 [原规划](../phase-1.5-head-fixed-live-r01/plan.request.json)及[两次相同正文](../phase-1.5-head-fixed-repeat-r03/RESULTS.md)换路复测。原批已经停止。本批独立上限为三次 HTTP，规划一次、相同正文两次。程序将原 JSON 请求的 `model` 替换为 `gpt-6.1-sol`，向 `https://aiapi.world/v1/responses` 发送。保留原 Prompt、Schema、`reasoning.effort=none`、`temperature=0.2`、`max_output_tokens=8000`、`stream=false` 和 `store=false`。正文依然绑定 r01 通过审核的规划及 C 示例材料。复测规划独立评估。

- [授权和摘要](approval.json)、[规划请求](plan.request.json)、[两次正文的同一请求](draft1.request.json)。
- 终端入口 `sh /tmp/edumind-t111-aiapi-r04/run.sh`。AIAPI Key 只经一次终端隐藏输入。受限单进程依次发送，无自动重试、回退或全批应用截止，网络操作超时设置为 90 秒。HTTP、传输和响应协议错误立即停止，完整且协议合格的 HTTP 响应在本地教学内容校验失败时仍可测后续独立样本。
- 每次出站前记录请求摘要。响应按接收块写入本机私有加密原件库，保留停止和部分响应，原件库无独立抗回滚保障。输出 token 参数及用量收据无法给出实际扣费硬上限。
- 沿用原本地规划转换、正文校验、四题相同重复成员恢复及[独立审核标准](../phase-1.5-head-fixed-t111/review-policy.md)。记录 Provider 自报的模型、回显参数和用量。Relay 上游实际执行情况与账单不可独立验证。
- 本次以原请求为对照，不会将复测规划换入正文，也不对过期应用操作写入。独立评估仅归于对应样本，不替代实际应用中的完整课程验收。

定向离线检查使用原件作为 MockTransport 输入，核对准确三次请求、两次正文请求字节相同、用量回显、原件回读及 HTTP 503 首次停止。无真实调用的检查结果不计入复测。
