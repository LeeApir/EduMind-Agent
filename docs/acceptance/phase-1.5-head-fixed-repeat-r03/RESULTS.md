# T111 三次真实请求结果

三次均已完成 HTTP 请求并收到完整响应。第 3 次与第 2 次的请求字节相同。第 3 次通过结构与事实引用校验，独立教学评估判定不得准入。

| 次数 | 内容 | 结果 |
| --- | --- | --- |
| 1 | r01 规划 | HTTP 200，真实规划和语义评估通过。旧应用操作在语义评估完成前已超时，保留 v1 大纲。 |
| 2 | r02 正文 | HTTP 200，完整响应 17,098 字节。第 5 段引用不存在的 `trace_step_11` 与 `trace_step_12`，本地拒绝。 |
| 3 | r03 正文独立取样 | HTTP 200，完整响应 15,821 字节。严格结构和引用通过，教学评估停止。 |

[第 1 次记录](../phase-1.5-head-fixed-live-r01/RESULTS.md) · [第 2 次记录](../phase-1.5-head-fixed-continuation-r02/RESULTS.md) · [第 3 次收据](repeat.body.json)

第 3 次候选摘要为 `c0206d4673b9277b4f80e2ed5308dd782d948c15de863439e307ca9a73e86324`。独立评估定位到正文第 2 段将模板中先写 `data` 再写 `next` 的顺序说成 C 语义要求，并发现 `questions.unreachable_count.stem` 缺少分配成功前提。后者在分配成功与失败时分别得到 1 和 0，题面没有唯一答案。[独立教学评估](TEACHING-ASSESSMENT.md) · [候选绑定的停止评估](independent-review.json)

已从三批原件库核实各有一次真实尝试。第 2、3 次请求 SHA-256 相同，完整响应的字节数和 SHA-256 均与收据一致。严格回读通过，第 3 次无格式恢复，候选无修订父稿。每批均有 STOP，额度已用完。未产生可准入课程，T111 保持 blocked。[第 3 次原始响应](repeat.raw.json) · [原件索引](originals-manifest.json) · [STOP](STOP)

本轮回读、离线 MockTransport、独立教学评估均新增真实调用 0。Ruff、冻结包原件核对、工作流和 diff 检查通过。
