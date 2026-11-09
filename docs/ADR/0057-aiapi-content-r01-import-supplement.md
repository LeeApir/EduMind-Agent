# ADR0057 补充提案 · AIAPI content r01 封存正文私有导入

状态为待用户确认，交付任务 PHASE-1.5-T117。本条目单独新增，原 ADR0057 继续管辖旧 r05 候选。确认后，仅允许通过既有封存导入 CLI 将下表对应的单一候选导入本机专用开发库 `edumind_catalog_p15_t108_t112`。导入范围限指定本机访客的私有课程，新增 Provider 请求为 0。[原 ADR0057](0057-reviewed-archived-head-import.md)

| 绑定项 | 准确值 |
| --- | --- |
| 来源批次 | `head-fixed-aiapi-content-r01` |
| 候选摘要 | `633091fd1c05ab83212c0f0256024bb7422021ef2d044e890e88ad72f9cc2412` |
| 原发请求 SHA-256 | `4df87d4a2ab296d1deb4e1ae67ebe35bda0eceb02f3a548ab69cc172184409b5` |
| 加密原件解封后的 HTTP 响应 SHA-256 | `73775fd7ee539d80c699c2f474f8ff36176a213af224d8aa4c9fcede58c520bc` |
| 提取的原正文 SHA-256 | `b31938cd30802dcb17846bbb215e5e8dc0c5d2678d3f113567a966547a6571c9`，13,176 字节 |
| 已审规划摘要 | `0997615bbdb35b96df95904d4d4d1730d08a94a2f797091c04a48e484a6452ee` |
| 程序材料摘要 | `854939ffc212c5eafe2c20529e46152d4023d56f521d3cc57ed068be59087e5b` |
| 教学证据摘要 | `8a4c8b44ac01d0f72660c222ff849c45a014ee8157b3725031ad34f18a3d5553` |
| 封存结果及原件索引文件 SHA-256 | `1ff8204a5eddf7c449a2859b9c46a2e6b8e0299218548878605a5d50c54d9fa8` |
| 机械诊断文件 SHA-256 | `8c87ca67a13d5fc4da9ddbc070b2dfd19451c99e35a043291130a4bb30595900` |
| 独立审核记录 SHA-256 | `bedfa8151f5c369f0c3f8a41e639f15bc69778c8986c1051b8e6c3997daab8dc` |
| 全文审核报告 SHA-256 | `14a1acf2bd7697ef1b8b4093e2dafed7c4bfead3df9c366ab92cec20c73625cd` |

原件索引、机械诊断和独立审核是导入时必须同时通过的绑定。按索引从本机加密原件重提唯一助手正文，核对原发请求和 HTTP 收据，按原请求 Schema、已审规划及同版程序材料重算候选。四题情境代码必须逐字节匹配，包括末尾 LF。独立审核必须绑定同一候选、原响应、请求、正文、规划依据和教学证据，并记录十项通过与零阻断。正文、代码、轨迹和答案直接使用已验证材料。核对失败即停止写入。[封存结果及索引](../acceptance/phase-1.5-head-aiapi-content-r01/live-result.json) · [机械诊断](../acceptance/phase-1.5-head-aiapi-content-r01/body-diagnosis.json) · [审核记录](../acceptance/phase-1.5-head-aiapi-content-r01/teaching-review.json) · [全文审核报告](../acceptance/phase-1.5-head-aiapi-content-r01/ASSESSMENT.md)

实现只新增一个固定来源及其校验分支，由现有 CLI 显式选择 `--source head-fixed-aiapi-content-r01`。复用原导入事务、私有版本、原样正文装配和服务端练习，按访客与候选摘要幂等。沿用 `reviewed_archived_response_import` 来源，另记本批规则版本 `head-reviewed-archived-aiapi-content-r01-v1`。新建独立的私有课程及导入操作，交付首个完整版本 v2。旧 r05 入口继续使用原默认选择及校验。

新课程页面标明「AIAPI content r01 封存正文导入，独立教学审核通过」。模型请求值和响应标签均为 `gpt-6.1-sol`，响应回报 `store=false`，实际模型和留存状态未确认。原生成记录仍为 `HEAD_AIAPI_ENVELOPE` 和 STOP，已停操作及其 v1 大纲保留。温度 `0.2 → 1.0`、指令不一致和 Schema 回显差异留在原件及失败证据中。独立审核的 `admission_eligible=false` 继续记录原生成流程的判定，本条授权只适用于单独的封存导入。新增请求计数为 0，历史用量归原批。

完成条件是在本机实际浏览器中核对完整阅读、13 帧状态与代码高亮、播放／暂停／前后步／重置、四题错误和正确反馈、答案隔离，以及刷新后恢复同版内容和作答且无重复提交。验收记录绑定入口、课程版本和准确候选，随本地完成提交交付。

提案阶段的只读复核已通过。10 个封存文件的索引一致，原协议失败可重放，原正文和四题代码未发生字节变化，候选及独立审核绑定可重算，旧 r05 映射可读。应用写入为 0。
