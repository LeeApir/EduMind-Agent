# T056 分层审核契约冻结提案 r01

状态：待具体设计批准。开发分支 `codex/phase-1-t056-t070`，基线 `9b2c195`。本轮 Provider 调用 0。

用户已授权开发 T056–T070。原任务 T056 的第5条验收条件仍要求具体审核协议获批准后再实施 T057–T059，因此当前保存完整设计检查点，不标 T056 完成。

请审查：

1. [ADR-0017 A–D](../../ADR/0017-layered-review-responsibilities.md)：分层职责、未知学情、检查项及版本/发布边界。
2. [具体输入与政策契约](../../agents/layered-review-contract-v1.md)：角色/计划目标绑定、职责字段、检查项含义和T057–T059逐阶段版本。
3. [21类对照材料](cases.json)：设计预期，不是已执行的模型测试或人类真值签核。free_list归属错误必须检出，但不预定原历史样本为major，不编造已发生的内存安全错误。

关键选择：结果 resource-review-v4 的六个顶层字段/类别保持；unit新增 objectives 第六必检项；未知学情本身不拦截，但无据个性化具体留未决；分工待核验职责不复制为真实未决；新政策摘要不复用旧案批准。仍保持严重reject优先、硬门禁、原调用/时间/修正上限及正式质量阈值。

冻结清单 [manifest.json](manifest.json) SHA-256：

`79f6d18ffadb4b505f84e60a95f57f265f1784c9c3159c0c486e55e1d7f663fe`

[批准请求](approval-request.json)保持 pending/approved=false，未推定用户已批准具体字段。批准后登记准确摘要，完成并提交T056，随后串行开发T057–T059；T060节点策略和T065执行隔离仍各自形成具体可批准设计。不重复申请这次已有的批次开发授权。

[验证记录](validation.json)：3附件摘要、21类材料/唯一ID、8个设计相对引用检查通过；git基线逐字节核对224运行文件、220 reference文件、24既有ADR和560既有验收文件保持。首次路径校验遇Git非ASCII路径引号，改用NUL分隔后通过，保留记录。实际执行 `python3 scripts/check_catalog_workflow.py` 与 `git diff --check` 通过；没有实现或运行T057之后的行为测试，不伪造语义通过。

当前T040 blocked、catalog_only、旧失败/停止预算保持。未跟踪OM目录未纳入。此次不含真实Provider、课程人工签核、动态开放、C编译/执行或生产迁移授权。
