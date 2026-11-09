# T111 · AIAPI 正文单次复测

按用户在单次正文、300 秒读取超时方案之后回复的“继续”，从新批发一次。准确请求沿用 r04 的 [正文](../phase-1.5-head-fixed-aiapi-r04/draft1.request.json)，逐字节核对并绑定 [r04 的超时原件](../phase-1.5-head-fixed-aiapi-r04/originals-manifest.json)。目标接口、模型、提示词、Schema、示例和规划均沿用。仅将读取超时从 90 秒延长到 300 秒，其他网络超时为 90 秒。[单次授权和摘要](approval.json)

本机入口为 `sh /tmp/edumind-t111-aiapi-r05/draft.sh`，经终端隐藏输入 AIAPI Key 后出站。只占一个新请求额度，使用独立加密原件目录。单次完成、失败或结果未知即封存。账单金额取决于 Provider，超时可能仍在服务端执行。结构合格后按 T111 原标准独立评估正文，复测结果与实际应用验收分别记录。

离线使用 MockTransport 核对请求字节、地址、300 秒读取及其他超时、响应回读、超时保全和再次运行拒绝。两条路径通过，离线检查的 Provider 调用为 0。
