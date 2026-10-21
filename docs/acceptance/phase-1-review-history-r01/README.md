# 人工只读完整审核/修正历史 r01

修复维护CLI只显示最终四份审核、无法完整核对早期修正意见的问题。`show --body` 和显式 `--export` 现在按案件同owner/单元/操作查询全部已持久化审核，不把同计划的其他操作或其他用户混进来；摘要/list仍不显示正文。

新增只读投影 `learning_review_history.py`，不改变决定/发布路径、审核Prompt、预算、Schema或数据库模型：

- `automatic_reviews`保留原字段，扩展为全部完整审核记录，包含原始verdict、local_routing、findings、unresolved、锚点、请求/响应摘要。
- `review_history`按服务端记录时间再review_id稳定排序，保留case原来的四个final_review_ids并逐条标记is_final_for_case。并列时间的ID顺序不冒充实际网络调用顺序。“最终”只是该案件选用的记录，不代表已通过或已发布。
- `candidate_history`提供被本操作审核引用的各候选版本/场景版本/摘要/正文与对应资源审核ID，以及最终候选标识；不会加载同计划另一操作的候选。
- `candidate_revisions`列出同角色相邻已持久化场景版本的前/后ID、摘要与审核ID，明确相同正文的新候选也可能摘要相同。数据库没有保存完整修正请求wire，因此这只是版本对照，不声称能证明某句反馈导致哪个改动。
- `plan_history`提供本操作审核引用的所有owner-bound计划及输入/参考/政策摘要；案件原payload和case_digest保持不变。失效案件也可以回看，不能因此重新批准。
- `complete/issues`显式标出缺失的最终审核、计划或候选；绑定不一致或案件摘要损坏直接拒绝正文投影。complete仅表示当前持久化审核引用能在库中取全，不代表未返回的Provider请求也有审核记录，更不代表内容正确。

身份仍须受信本机allowlist。正文仅在明确--body/--export时读取；导出仍0600、显式新路径、不覆盖。新投影使用no_autoflush，不为调用方隐式写入待保存对象，不执行lock/commit/人工决定/发布或模型调用。

```sh
python scripts/review_learning_cases.py show CASE_ID
python scripts/review_learning_cases.py show CASE_ID --body
python scripts/review_learning_cases.py show CASE_ID --export /absolute/private/new-case.json
```

实际验证见 `pg-check-01.json`：新隔离PostgreSQL，4个测试文件22通过0跳过。新独立测试构造两次资源修正：6审核/5候选/2版本对照/最终4标识；同owner/单元/计划但不同操作、另一owner不串入；摘要无正文、反复读取稳定、失效案件可回看、导出0600不覆盖、读取前后操作/案件/调用数/发布/决定等不变，且不autoflush调用方新对象。缺失候选的旧合成夹具明确返回complete=false。

全部模型、维护人及课程都是合成测试。没有对真实A01签核，没有Provider真实请求或H调优。Ruff和两处源码mypy通过；旧四运行账本与H封存摘要保持。历史冻结包绑定的旧CLI源码保持为历史证据，不修改它们的manifest来伪装仍可重新执行。

交接：本任务仅修复现有ADR-0015要求的只读完整信息。下一T080准备计划纠错契约/预算/任务供用户确认；不实现计划重建、不扩自动修正、不变更T040 blocked。修正后的视图仍依赖人工实际核对，不能把“看得到历史”当作“计划错误已被解决”。
