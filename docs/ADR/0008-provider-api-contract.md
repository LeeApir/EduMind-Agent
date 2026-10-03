# ADR-0008 API契约落实（PHASE-1-T003）

依据已批准[ADR-0008](0008-provider-credentials-and-egress-boundary.md) A–D与[批准记录](0008-provider-approval-20261004.json)，新增契约保存于[OpenAPI](../api/openapi.yaml)。本文件不新增安全批准，也不声称端点已运行；新增操作以`x-runtime-status=planned`及实施任务注明未来交付。

连接集合/单项CRUD归T009，显式一次连接测试归T010，静态类型/能力及缓存模型列表/显式POST刷新归T011，四档偏好归T012。T004只建立持久化服务，T005只建立内存生命周期；临时secret上传HTTP入口也由T009交付。普通GET不访问Provider；测试/刷新POST需CSRF、单独预算及选中版本/模型/data categories的同意。

## 版本与凭据

- owner/session从Cookie派生，创建secret不得传user/session ID。所有响应`private, no-store`，Key/Key片段/指纹/密文/DEK不回传；无凭据字段不证明可调用。
- config_version从1开始，PATCH/DELETE必需`If-Match`十进制版本。PATCH与DELETE行锁后复核，冲突409；不接受客户端写入version。显示名等更新也递增配置版本并失效旧同意；provider_type/base_url变更清空旧secret，只有显式重新提供持久secret才可绑定新目标。
- DELETE留非敏感墓碑，清空secret/禁用/失效偏好。当前owner同一删除的旧版本重放204；其他版本409；跨owner/不存在404，过期认证401。不得复活墓碑或未授权清理学习历史。
- persistent创建必需secret；temporary/none创建禁止secret。PATCH secret=null清除，遗漏保留（目标变更除外）；最终模式必须与secret一致。原生secret字段整体加密，不接受任意settings/header。
- 临时secret上传只用于temporary连接，handle绑定owner/session/进程/连接版本/operation_id/purpose；内存等待≤5分钟、会话内待领取≤4，总operation≤180秒且不能越过会话到期。handle不是鉴权，不能塞队列或URL。跨进程丢失返回CREDENTIAL_UNAVAILABLE，重新输入，不自动持久化。

## 能力、偏好与同意

能力每字段true/false/null（未知），含declared/verified/unknown来源与规则版本，不能凭模型名猜能力。模型列表GET只读缓存；POST刷新一次有界请求，失败保留旧快照。无缓存空列表不证明Provider没有模型，缺实际用量记null。

偏好优先级为任务临时覆盖→用户档位→用户默认→系统默认；T003定义四档存储契约，用户默认/临时覆盖的内部解析由T012交付。GET仅返回已配置四档；未配置可解析默认，但显式配置失效不能静默发送至另一个目标。审核模型不可用拒绝正式发布。

PUT使用expected_version（0仅创建），主route与每个fallback绑定connection/config_version/model/data categories，明确consent_accepted=true；fallbacks默认空、最多3目标，只允许限流/超时/暂不可用触发，有序且每次重新验证/计数。跨连接同厂商也需要同意。

每次operation确认实际目标/模型和数据类别，不能把连接保存当永久数据发送授权；改变模型/目标/策略使旧同意失效。catalog_only仍关闭学习生成，设置和测试入口不解除门禁；测试/刷新无预算时403 BUDGET_NOT_AUTHORIZED、无隐式出口。

## 安全错误语义

所有错误只含code/message/retryable，固定文案不含输入或供应商原错误。401 UNAUTHORIZED；403 CSRF_FAILED或BUDGET_NOT_AUTHORIZED；404 NOT_FOUND；409 VERSION_CONFLICT/CONSENT_REQUIRED/CREDENTIAL_EXPIRED/MODEL_UNAVAILABLE/FEATURE_UNAVAILABLE；422 VALIDATION_ERROR/INVALID_TARGET/CAPABILITY_UNAVAILABLE；503 CONFIGURATION_MISSING/CREDENTIAL_MISSING/CREDENTIAL_UNAVAILABLE/TEMPORARILY_UNAVAILABLE；显式探测429 RATE_LIMITED、502 AUTHENTICATION_FAILED/INVALID_OUTPUT、504 TIMEOUT。实际响应选具体条件，不把模板示例的单一码当所有条件；未知capability不出站。

T007实现发送边界行锁和状态复核，T005实现期限/取消；T003定义接口语义，不用纸面契约冒充运行保证。
