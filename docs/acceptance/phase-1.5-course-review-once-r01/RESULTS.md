# T096：单次课程审核结果

用户要求直接发送 T095 未发送的审核请求。独立单次向 AIAPI `gpt-6.1-sol` / `low` 发送原请求 **1 次**，请求 79,305 字节，SHA-256 `2846ee4c890c6a8cc082ec76d5da27d01adccf6521d336c1ecd68168ce3bc7e5`；HTTP 200，未重启 T095。

模型最终文本给出 `verdict: pass`、`issues: []`。该 JSON 按冻结 Schema 的本地约束校验通过，candidate_id 与准确课程候选绑定。完整意见见 [review-output.json](review-output.json)，完整原始响应见 [response.bin](response.bin)。模型没有给出逐题或逐块理由；pass 是建议，并不证明课程正确。

**完整协议校验未通过**：响应的 reasoning 项包含非空 `encrypted_content`（1,996 字符），现有审核适配器不接受该字段的非空内容；执行入口按 `UNRECOGNIZED_REASONING_CONTENT` 停止，未解密或改写原响应。另有独立用量问题：服务自报输入 **32,786**、输出 **98** token，输入超过本单次本地预约 **32,768** 18 token；复用的 `observe_course` 仍有更严的原 8,192 输入上限。原函数首先因推理内容失败，故未到该用量门；不能将本次记为完整协议通过或在事后追认为通过。

其他观测：返回模型 `gpt-6.1-sol`、reasoning `low`、响应 schema 回显匹配，instructions 回显为原指令加已知 37 字符尾缀；这不证明完整上游上下文、真实路由或身份。原始响应 SHA-256 `91e050d772be6113956e622650dd7bf6a24e660d9577fdac76fe013b654e58ff`。实际账单未知。响应和请求及状态原件另保存在 `/private/tmp/edumind-p15-course-review-once-r01`（0700/0600）。

原 T095 仍停止；本次未重试、补样或自动修复，未完成课程质量验收或 T038。用户可对模型意见及 [课程候选](../phase-1.5-combined-candidate-r01/results/course.md)进行判断。
