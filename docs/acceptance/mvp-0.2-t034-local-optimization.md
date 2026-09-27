# T034：连接生命周期优化与非计费交接

本轮真实付费Provider调用0；没有读取/修改真实.env、切模型或push/merge。
T033已完成f839a07；T034本地修复通过不等于T032真实验收通过，T032仍blocked。
指标与关键路径纠正见mvp-0.2-t033-nonbillable-diagnosis.md，旧失败JSON均未修改。

## 局部修复

backend/app/core/database.py新增DatabaseRuntime及database_lifespan；main.py注册lifespan。
在每个ASGI lifespan的请求state内lazy创建一个engine/sessionmaker，关闭时dispose。
只复用连接池，不复用AsyncSession、事务、画像或owner状态；pool_pre_ping保持。
避免原每请求销毁engine后StreamingResponse流体重建物理连接的等待。
/health无需DB配置；无lifespan的嵌入式调用保留旧按请求创建的兼容路径。
没有改变SQL/schema/API、目标识别、画像模型/合并、显式修正、路径版本、审核或Provider请求。

首版app.state复用在全量owner测试中失败：两个同时存在的TestClient不同loop共享engine。
已改为ASGI lifespan yield出的request.state，每个lifespan/loop独立池，原owner测试通过，
没有修改断言、屏蔽异常或跳过失败测试。生产连接复用不是全局跨loop单例。

## 实际控制实验（不是模型P95）

真实loopback Uvicorn HTTP/1.1 → 原路由 → 隔离PG，Provider固定FakeAdapter。
每次真实asyncpg物理连接前注入100ms；legacy模式只覆盖DB dependency以重现原创建/dispose行为。
两模式执行同样公开学习目标、完整schema/审核发布、同键恢复、本人GET200和外部owner GET404。
最终证据mvp-0.2-t034-pool-latency-v3.json：

| 指标（客户端POST起点） | legacy | lifespan池复用 |
| --- | ---: | ---: |
| 学习POST新物理连接数 | 2 | 0 |
| HTTP首字节 | 239.316ms | 38.318ms |
| 完整HTTP头 | 239.327ms | 38.324ms |
| SSE状态 | 239.356ms | 38.343ms |
| 确认教学正文token | 399.024ms | 44.756ms |
| 完整教学段落 | 399.108ms | 44.813ms |
| 正式发布 | 457.691ms | 84.146ms |
| 本轮mock Provider尝试 | 8 | 8 |
| 同键恢复新增Provider | 0 | 0 |

首段提前354.294ms；其中明确去掉2次注入冷连接延迟共200ms，其余差异包含查询/调度/缓存噪声，
不把全部差值归因于连接等待。匿名会话请求本身先建立一条池内连接；这是产品必要步骤，
不是额外计费预热。对后续并发池扩张/连接失效不保证零物理连接，也不证明真实模型秒级达标。
画像Provider仍在首屏关键路径，优化没有移出或省掉画像调用。

v1/v2控制结果均保留；v1的fake_provider_calls为累计数，且外部owner测试误用不存在路径，
只能说明时延，不能证明owner边界。v2改为单轮8/8、正确GET本人200/外部404。
v3基于最终request.state生命周期版本，作为本次最终控制证据，不挑最快值代替计划P95。
曾误用不存在的test_profile_correction.py导致no tests ran；更正为实际profile_api等全量回归。
新增路径测试曾把nodes字符串列表误读为对象，现使用真实node_details校验，不改产品响应。

## 回归与限制

tests/test_database_lifespan.py：lazy health、同lifespan factory复用/关闭、新lifespan隔离；
真实池分支验证显式手动修正code_first、后续画像合并version3、路径绑定profile_version3、
当前C指针前置及推荐code，所有资源审核passed，同键POST不增调用。
test_first_screen_pool_latency.py：真实wire、冷连接归因、完整首段更早、same-key恢复、owner GET边界。
原test_learning_sessions、test_owner_reads及web/tests/learningRecovery.spec.ts均保留。

计时补强：无空行正文后接代码围栏不会伪造结束边界或丢失正文；到temporary结束才确认。
孤立Markdown **等格式符不是教学正文token；未知教学意义仍需hash绑定人工decision。
audit_first_screen_v2.py独立处理全20样本，重复编号拒绝，未确认/超时/中断保留，不覆盖raw。
任意非空delta与确认教学正文仍是不同指标；原T032 raw/audit JSON原样保留。

最终验证：backend隔离/mock pytest416通过、0跳过、9条弃用警告（其中2条来自新增真实Uvicorn测试
触发既有websockets依赖）；Ruff app/tests/docs/acceptance通过，Mypy55源文件通过。
前端66测试/11文件、typecheck/build通过；ESLint0错误/67已有格式警告。git diff --check通过。
测试与控制证据均非计费，不能证明当前实际Provider的HTTP首字节/教学token/首段P95达标。
当前model网络延迟、排队、真实画像占比仍未知；历史20样本不足以反推这些阶段耗时。

## 需要产品决定的部分（未实施）

若继续大幅压缩画像串行等待，需要决定是否让首段/首路径基于旧或保守画像，
之后如何绑定新画像版本/手动修正、重规划冲突与失败语义。
当前路径读取已合并的engineering_preference和版本；直接跳过、后台化或并行使用旧版本
会改变已批准学习行为或数据契约。本轮停止该部分，不擅自改变API/PRD。
下一轮真实有限复测计划另见mvp-0.2-t032-retest-plan-v2.md，尚未执行。

交接：T033测量修复与T034局部优化独立本地完成提交；T032保留blocked，待另行确认复测。
不归档MVP0.2或进入0.3；测试启动的Uvicorn已关闭，隔离库不清空、不动原Compose服务。
