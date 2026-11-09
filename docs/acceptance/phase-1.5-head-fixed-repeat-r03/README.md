# T111 r03 最后一次取样

用户在 r02 停止后要求继续。本批以 r01 规划和 r02 首稿尝试为前两次，只有一次新增真实请求。请求与 r02 首稿逐字节相同，SHA-256 为 `fccba92a41527dbcd9da34ceefca77ca1ee1edaa33c83a49e1ffbc3940e1c92d`。这次独立取样记录模型在同样材料下能否提供有效事实引用。

批次不设全程截止。请求使用原 90 秒 I/O 超时和相同响应校验，通过前台隐藏输入 Key。原始响应另存于私有 vault，结果按同一校验标准记账。

离线核验已回读 r02 停止记录和完整响应。MockTransport 验证了有效首稿与非法事实引用两种结果均保留原件，入口在一次尝试后拒绝重复发送。离线检查新增真实请求为 0。

[本次授权](approval.json) · [准确请求](repeat.prepared-request.json) · [r02 失败证据](../phase-1.5-head-fixed-continuation-r02/RESULTS.md)
