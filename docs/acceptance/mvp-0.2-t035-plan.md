# T035 冻结三样本诊断

用户2026-09-27明确批准。独立3样本，不是正式20样本的预热或补跑，不计算P95。
单并发，零计费预热，固定公开目标，匿名新owner每个一次；POST总截止180秒。
全局36次实际adapter调用包含内部重试；认证/余额/配额异常立即关闭后续调用。
保守将CAPABILITY_UNAVAILABLE也视为停止原因，避免402归一化后继续调用。
无客户端生成重试，无替换样本。未发样本记录unattempted。当前配置模型和传输不改变。
只读恢复GET不触发生成，不用重新生成模拟恢复。

口径/段落规则原样沿用T032 v2：真实socket首响应字节、HTTP头收齐、完整SSE状态、
任意delta、hash绑定人工确认教学正文首token和完整段落、scene_ready独立。
首段空行或临时流结束边界；排除标题代码，导语后继续审核；不明语义保留未确认。
客户端和校验后两套时钟，匿名HTTP与客户端准备另列，完整旅程加上准备耗时。
phase span为嵌套包含时长，不能直接相加；画像总时长减提取是DB/合并残余，不冒充纯合并。
新匿名owner无旧画像，合并保留逻辑仍走原实现，但无需执行旧画像merge。

真实Vite4182 → Uvicorn8012 → 新edumind_perf_t032_diag3 PostgreSQL，当前Provider网络。
连接池物理connect/checkout计数只记数字；从真实adapter入口到首delta/结束记单调时间。
trace不记录参数/SQL/ownerID/URL/凭据；仅固定公开目标候选正文可出证据。
独立保存raw、ledger、trace、人工decision/audit；历史证据不覆盖。
工具mock先验证，最终停止本次服务，保留隔离DB。T032仍blocked。
