# MVP 0.2 T032：当前模型首段性能复测

结论：未通过，任务 blocked；冻结计划已执行一次，不补跑。
日期：2026-09-27。前置真实浏览器 T031 完成提交 2ff61f7，重试修复 fb273c7。
不归档 MVP 0.2，不进入 MVP 0.3，不 push/merge。

## 测量与结果

20 个正式样本，单并发，固定单链表/C 学习目标，每次新匿名 owner 和幂等键。
0 个计费预热，第一个样本保留；每个 POST 总截止180秒，完整消费 SSE。
HTTPX 0.28.1 → 实际 Vite 4182 → Uvicorn 8012 → 全新隔离 PostgreSQL
edumind_perf_t032（Alembic 空库迁移至0009）→ 当前 Provider，无 mock。
单 Worker 全局240实际适配器尝试上限，包括现有 Gateway 重试；实际162次，停止服务后账本无 started。

用户在本任务回复“同意”，批准计划文件里的段落规则、校验后起点和有限预算。
验收入口只包装 FastAPI 已解析的 endpoint call：身份、依赖及请求 schema 通过后记录同机
monotonic_ns，实际原 endpoint 原样执行，返回时仅增加验收专用时间戳头。
生产源码/OpenAPI/auth/审核/owner边界/Provider请求不变。无效 schema 和401不会取得该头。
客户端还单独记录 POST 发起时间；HTTP头、SSE状态、有效模型内容token、正文候选边界、
scene_ready 分别计时，不把状态或头当成模型内容。
token 是客户端收到的首个有效临时模型内容 delta，不是厂商内部生成时钟或网络原始首字节。

最近秩 P95 = 排序第19/20位，缺失按 +∞，条件分布不能代替全部计划。

| 指标 | 校验后 P95 | 客户端 POST 起点 P95 | 判定 |
| --- | ---: | ---: | --- |
| HTTP响应头 | 4563.092ms | 4589.209ms | 独立传输指标，无内容门槛替代 |
| 首SSE状态 agent_start | 4563.329ms | 4589.446ms | 独立状态指标 |
| 首有效临时模型内容token | 5661.935ms | 5699.237ms | **失败：目标≤2000ms** |
| 语法段落候选（非验收结论） | 6015.980ms | 不用于通过判定 | 含3个无法确认教学意义的候选 |
| 人工确认教学首段（全计划） | 缺失3/20，P95不可确认 | 缺失3/20 | **未通过：不能证明≤10000ms** |
| 教学首段条件分布，仅17个确认样本 | 6260.461ms | 6297.763ms | 不是全20样本通过证据 |
| 正式资源发布 scene_ready | 32351.182ms | 32379.777ms | 另列总生成，不是首段 |

20/20 正式发布成功，HTTP/完整学习请求失败率0%，180秒总超时0，未发样本0。
隔离PG只读聚合确认20操作、20不同owner、20不同幂等键、20不同正式单元，均published。
首token范围3626.122–5731.441ms，0/20达到2秒。
段落候选未确认率3/20=15%；这不是“后续全文没有教学内容”的断言。
实际适配器尝试失败2/162=1.23%，均 TIMEOUT（账本23和36），现有契约重试后完成；
失败尝试保留，不能因为最终请求成功就称Provider零失败。

## 逐样本教学意义核对

原始测量 JSON 保留 manual_semantic_review_pending=true，不改写原始数据；
独立 audit JSON 记录人工核对完毕及失效候选编号。段落哈希/字符数在原始 JSON 可逐项绑定。
仅首个语法候选输出到运行工具供执行者核对；不保存完整临时模型原文或私有画像。

| 编号 | 核对结论 |
| --- | --- |
| 1、6、7、8、10、13、14、15、17、18、19 | 完整说明指针存地址、变量框和目标对象/地址的箭头关系，确认 |
| 3、4、5、9、16 | 完整给出地址标签箭头与分离变量框/对象的图示表征方法，确认 |
| 20 | 给出节点盒子、地址与指向下一个节点的连接图示，确认 |
| 2 | 只有临时解释说明及先看清/再学习的导语，未实际完成概念解释，不能确认 |
| 11 | 仅要求稍后通过C代码观察，没有实际代码或已完成教学说明，不能确认 |
| 12 | 自称学习目标及要用图看懂的导语，未实际给出地址/对象关系解释，不能确认 |

遵守已批准“不能确认教学意义则未满足”，不凭句号、字数或目标声明放行。
测量工具只保留第一个语法候选的时刻；人工否决后，不能从剩余记录重建更晚教学段落时刻。
因此这3个样本首段记为未确认，而不是猜测时延或补跑替代。剩余限制是测量证据缺失，
不是证明这3个模型流永远没有教学正文。今后若复测，应在采样前离线验证所有候选边界时间的
采集与人工选择流程，但本次不会修改已执行计划或新增付费样本。

## 模型、指令与环境

配置/结构化返回均 deepseek-v4-pro-0813；文本 Responses streaming，结构化 responses_json_schema。
profile-v1/profile-instructions-v2；learning-resources-v1/learning-resources-instructions-v8；
resource-review-v3/resource-review-instructions-v2。首屏无独立版本常量，源码 SHA256：
0169bf5acbbabd38a2c8da2e66b0f70c3d73ba1babdc20bc443f177a2312a57c。
业务基线19e4ac2，首屏/模型生产代码未修改。

macOS15.6.1 arm64，Python3.11.16，FastAPI0.115.12/Uvicorn0.34.0/Vite6.1.0。
当前主机出站网络；Provider adapter和HTTPX均trust_env=False，SSRF校验保持。
本地HTTP CLI为Secure会话Cookie复制到仅进程内的loopback cookie jar，未降低服务端Cookie设置；
A的真实浏览器Cookie/CSRF验收仍独立有效，B不冒充浏览器渲染性能。
服务进程/依赖已启动，无计费预热；Provider冷热/缓存/排队状态未知。
本机还有既有Compose服务，采样初期及后半段并行运行过离线回归/静态检查；
没有做空闲机器负载控制，不宣称严格隔离CPU的厂商性能基准，不丢弃受影响样本。
这是一种固定目标/前置C指针的有限验证，不证明全10知识节点、公网部署或高并发性能。

162尝试：20 stream、142 structured，160 completed、2 TIMEOUT。
结构化成功响应可取得的用量合计input133395/output32536 tokens；stream及失败尝试用量未采集，
这些不是全部计费用量，费用和剩余额度未知。当前真实.env只读加载，没有修改、输出或切模型。

## 定位和限制

源码确认首SSE/HTTP头前先等待画像结构化Provider调用、画像落库和路径准备；随后才开始文本流。
当前数据中HTTP头就已接近3–4.6秒，接着等待首内容，符合串行准备带来的首屏延迟风险。
没有Provider内部排队/网络分段计时，不能把全部延迟归因于模型或声称已量化画像调用占比。
需要后续独立任务讨论首屏关键路径和首段提示约束；本验收不改变画像、安全或审核API重大决策。

首次服务启动忘记只读env-file，安全拒绝缺失配置，0尝试、0正式样本；修正启动命令后采样。
不是模型失败，也没有重置已消耗账本。最终全部20样本和2次真实TIMEOUT保留。

## 脱敏证据与复现

- 冻结规则：mvp-0.2-t032-first-screen-plan.md。
- 原始20样本：mvp-0.2-t032-first-screen-results.json。
- 人工核对/全计划门槛：mvp-0.2-t032-first-screen-audit.json。
- 162实际尝试：mvp-0.2-t032-provider-ledger.json。
- 入口：serve_first_screen.py / run_first_screen.py / audit_first_screen.py。
- 离线回归：backend/tests/test_first_screen_measurement.py、test_real_browser_budget.py。

需要事先配置全新perf_t032隔离库、当前服务端环境和另行批准的采样计划/预算。
不能覆盖本次结果，不能把复现命令当作再次调用授权。命令不含密钥：

```text
# backend，EDUMIND_DATABASE_URL由本机环境指向隔离PG
uv run --frozen alembic upgrade head
uv run --frozen --env-file ../.env python ../docs/acceptance/serve_first_screen.py --confirm-billable --ledger ../docs/acceptance/<fresh-ledger>.json
# 项目根，另一个终端
EDUMIND_API_PROXY_TARGET=http://127.0.0.1:8012 pnpm --dir web dev --host 127.0.0.1 --port 4182 --strictPort
# backend，另一个终端，冻结20样本，无客户端重试
uv run --frozen python ../docs/acceptance/run_first_screen.py --confirm-billable --output ../docs/acceptance/<fresh-results>.json --ledger ../docs/acceptance/<fresh-ledger>.json
# 按公开候选实际人工核对，不照抄本次编号到新结果
uv run --frozen python ../docs/acceptance/audit_first_screen.py --results ../docs/acceptance/mvp-0.2-t032-first-screen-results.json --output ../docs/acceptance/<fresh-audit>.json --unconfirmed-paragraphs 2 11 12
```

后端隔离/mock回归403通过、0跳过、7个已有警告，Ruff通过、Mypy55源文件通过；
前端66测试/11文件通过，typecheck/lint/build通过；前端67个已有格式警告，0错误。
离线 TestClient/MockTransport 只验证测量工具，不代替本次20次真实HTTP/Provider链路。
采样服务8012和代理4182已停止；保留隔离数据库用于只读调查，不触碰原服务8000。

交接：A已完成；B保留阻塞及失败证据，原始结果不可覆盖。
不创建Task-Completed，不声称具备本次补充验收的阶段切换条件。

## 2026-09-27 追加口径纠正（历史数据不改写）

上述headers实测的是HTTPX收齐响应头，不是原始HTTP首字节；token是任意非空temporary delta，
并非经独立资格评审的教学正文首token，也不能称为HTTP TTFB。
旧raw无法重建这两项真实时刻；保留旧数值/失败证据，但不把旧“首token失败”标签推导为
精确HTTP首字节失败。完整说明及非计费诊断见mvp-0.2-t033-nonbillable-diagnosis.md；
局部连接优化及控制实验见mvp-0.2-t034-local-optimization.md。T032仍blocked，未真实复测。
