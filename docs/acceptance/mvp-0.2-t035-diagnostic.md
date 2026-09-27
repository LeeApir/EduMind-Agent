# T035 三样本真实诊断（非正式性能验收）

2026-09-27执行，基线415b6df + 本任务验收专用工具。T030 fb273c7及T034已完成。
严格一次3样本、单并发、0计费预热、POST整体180秒、全局36实际adapter尝试。
实际24/36次：3 stream +21 structured，全部completed、每样本8次，无内部重试、超时、
认证/余额/配额异常；不替换失败、不追加补跑。操作发布3/3；最早教学段落确认2/3。
3样本仅诊断，无P95、无正式通过声明，不混入未来20样本。T032继续blocked。
17:44:33确认本次Uvicorn/Vite均停止、8012/4182无监听，原Compose服务未动。

## 当前配置与环境

本轮只读加载真实.env，**当前配置及structured返回均为deepseek-flash**。
这与历史T032的deepseek-v4-pro-0813不同；本轮没有切模型或修改.env，不能把结果当Pro优化对照。
structured为responses_json_schema、正文Responses streaming。
profile-v1/profile-instructions-v2、learning-resources-v1/learning-resources-instructions-v8、
resource-review-v3/resource-review-instructions-v2；首段无单独版本，用first_learning源码SHA。
四个指令源码摘要、macOS/Python/HTTPX实际版本在raw.environment及instruction_source_sha256。

真实localhost HTTP/1.1 socket → Vite4182实际代理 → Uvicorn8012单worker →
独立PostgreSQL edumind_perf_t032_diag3（0009 head）→当前Provider真实网络。
所有样本使用同一公开目标“我想理解单链表的前置知识，先看 C 代码。”，新匿名owner/key。
采样时未并行跑工程测试，无计费预热；第一样本不丢弃。Provider缓存/冷热/排队、
公网路由/带宽及机器瞬时负载未测，不能推断Wi-Fi或厂商排队。
凭据、Cookie/CSRF、Provider URL、owner/operation ID、画像和完整流未出证据。
固定公开候选正文保存供语义评审；出现疑似代码候选如实保留，不算教学段落。
结构化调用已报告22608输入/3724输出tokens；stream usage不可得，非完整账单/货币费用。

## 指标（ms，客户端learning POST起点）

| 样本 | 匿名HTTP / 全准备 | HTTP首字节 | HTTP头收齐 | SSE状态 | 教学正文首token | 完整可学习首段 | 正式发布 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 85.148 /110.003 | 1342.659 | 1342.687 | 1342.747 | 未确认 | 未确认 | 17620.179 |
| 2 | 10.389 /17.623 | 1588.895 | 1588.940 | 1588.983 | 2476.139 | 2847.886 | 14110.439 |
| 3 | 9.802 /16.561 | 1161.363 | 1161.375 | 1161.410 | 2159.223 | 2230.695 | 12219.559 |

匿名HTTP是guest请求发起到完整响应；全准备包括HTTPX建立等客户端必要开销，不冒充纯DB。
完整用户等待（含匿名全准备）：HTTP首字节1452.663/1606.517/1177.925；
首段未确认/2865.508/2247.256；正式发布17730.183/14128.061/12236.120。
校验后正文token：未确认/2467.431/2150.512；完整首段未确认/2839.178/2221.983。
任意非空delta：2894.529/2476.139/2159.223，仅调试，不替代正文token。
三个HTTP首字节观测均低于2秒，但不计算P95；两个已确认正文token高于独立2秒内容门槛。
发布成功不等于首段通过；正式资源时长不替代首段指标。

## 独立语义评审

采集时不自动通过；全部15候选另存hash绑定decision，审阅使用原单调到达时刻。

- 样本1共10候选：1/2为标题与目标导语；3是编号列表，句点只是编号，不是句末标点；
  6是表格，句点来自C成员表达式，不能凭机械sentence_terminated=true放行。
  3/6保持unconfirmed；4/5/7导语，8/9代码排除。候选10含完整教学总结，可确认教学意义，
  到达5348.784、完整5672.029ms，但前面的资格未知，不能称它是最早正文token/首段。
- 样本2共4候选：1虽以导语起头，但明确教学事实“指针存的是地址”和链表前置知识，
  完整句/空行齐全，确认teaching；2标题，3完整赋值/遍历知识可确认，4邀约。
- 样本3唯一候选直接说明指针保存地址及读代码方法，完整教学句，流结束边界确认。

未确认样本1不丢弃、不当通过，不拿后段绕过前候选。

## 真实关键路径（ms）

| 阶段 | 1 | 2 | 3 |
| --- | ---: | ---: | ---: |
| Cookie/CSRF与DB鉴权 | 4.482 | 5.373 | 3.733 |
| 幂等操作预留DB | 11.266 | 3.480 | 4.932 |
| 知识节点识别 | 2.493 | 0.075 | 0.098 |
| 画像提取整体（Provider+schema） | 1055.417 | 1537.314 | 1107.322 |
| 其中实际画像adapter调用 | 1054.050 | 1535.933 | 1105.275 |
| 画像提取前DB读取 | 7.492 | 1.597 | 1.678 |
| 提取后合并/锁/flush/DB | 24.374 | 13.024 | 14.103 |
| 路径锁/快照/计算/DB | 30.082 | 18.450 | 17.698 |
| 准备整体（包含画像和路径） | 1118.500 | 1571.580 | 1145.785 |
| 首段Provider入口到首非空delta | 1539.694 | 877.091 | 990.037 |
| 首段Provider整个流 | 4321.247 | 3228.862 | 1063.638 |
| 后续正式生成/审核/发布整体 | 11932.475 | 9273.168 | 9977.725 |

嵌套span不能重复相加。提取后阶段按真实函数边界差值，不等于纯CPU合并；
新匿名owner没有旧画像，merge_profile_snapshots无需运行，但验证/owner锁/写入路径不跳过。
路径在画像完成后才开始，响应头在准备完成后发出，首段Provider在状态DB更新后进入，
顺序由trace纳秒证明，不凭猜测归因模型。节点命中显式别名，本轮不调用目标识别模型。
两次必要Provider工作串行，是秒级正文等待主项；DB/路径为毫秒级。
样本1 POST鉴权结束到endpoint validated存在约199ms未细分空档，不能归因数据库或模型；
依赖初始化/调度候选需另行非计费诊断，trace明确保留，未假称所有耗时均已解释。
重复stream状态读取/更新全部时段在trace和audit-v2.repeated_db_spans_ms，不只取末次值。

## 连接复用与恢复

第一匿名会话建立1条物理连接，其后总共0条新连接；各learning POST有8次checkout但0connect。
三个恢复GET各200/published、checkout2/物理connect0，账本增量均0。
只读DB聚合3 published/3 owner/3 key；没有第二个生成操作。
本轮只验证完成后的持久化恢复，不新增断线注入或运行中取消测试；T030原有运行中/失败/
迟到响应回归及T031真实断线证据仍有效。本轮不宣称账单级exactly-once。

## 工具可靠性与新发现

socket首字节与头收齐/SSE确实分开；单调时钟、多候选、hash绑定独立评审、
未确认阻止最早声明、有限预算/零新增恢复均能工作。13针对性offline回归通过。
机械标点字段不是资格判定，列表编号/成员句点造成false-positive候选，但独立评审正确拒绝。
正式验收前应非计费强化判定辅助字段，保留人工语义判断，不能降低规则放行表格/无句末列表。

样本1有列表粘连和代码候选越过围栏。源码learning_sessions.py:76以delta.text.strip()
为发送条件，确定会丢弃独立纯空白chunk；这会让原始换行/围栏/段落与客户端流不一致。
本轮未保存Provider原始正文流，不能断言样本1的每处格式损坏都由此造成，不能排除模型本身格式。
这是确定的代码风险及实际异常形态证据，不在采样中途修改生产链、重跑挑样本。
建议独立非计费修复保留安全的空白chunk，补真实路由跨chunk/围栏回归，再决定新的冻结正式基线。
画像串行若要后台化仍涉及偏好/版本/显式修正契约，需要产品决定，本轮未做。

## 复现与实际验证

命令从backend运行（隔离数据库URL通过进程环境提供，不修改.env）：

```text
uv run --frozen alembic upgrade head
uv run --frozen --env-file ../.env python ../docs/acceptance/serve_diagnostic_three.py --confirm-billable --ledger ../docs/acceptance/mvp-0.2-t035-ledger.json --trace ../docs/acceptance/mvp-0.2-t035-trace.json
# root另一个终端
EDUMIND_API_PROXY_TARGET=http://127.0.0.1:8012 pnpm --dir web dev --host 127.0.0.1 --port 4182 --strictPort
# backend，一次3样本，旧输出已存在，复现需新授权/新DB/新路径，不能覆盖原证据
uv run --frozen python ../docs/acceptance/run_diagnostic_three.py --confirm-billable --ledger ../docs/acceptance/mvp-0.2-t035-ledger.json --output ../docs/acceptance/mvp-0.2-t035-raw.json
# 此后全部不计费
uv run --frozen python ../docs/acceptance/audit_diagnostic_three.py --raw ../docs/acceptance/mvp-0.2-t035-raw.json --decisions ../docs/acceptance/mvp-0.2-t035-decisions.json --trace ../docs/acceptance/mvp-0.2-t035-trace.json --output <fresh-audit-path>
EDUMIND_TEST_DATABASE_URL=<isolated regression DB> uv run --frozen pytest -q
uv run --frozen ruff check app tests ../docs/acceptance
uv run --frozen mypy app
```

后端421 passed/0skip/9既有弃用警告；Mypy55源文件通过。Ruff初次新增测试导入排序错误，
修正后全量通过；最终针对性13passed。前端66测试/11文件通过，typecheck/build通过，
lint0错误/67既有格式警告；实际执行pnpm --dir web test --run/typecheck/lint/build。
audit-v1保留，v2补充提取前后细分与重复DB时段列表，不覆盖raw或历史T032。
采样后仅补强验收工具的恢复GET失败不丢原生成证据、阶段缺失保留未确认路径；
针对性13测试再次通过，没有真实补跑或重新生成，原采样代码的生产链与指令未改变。
git diff --check及明确暂存自查；没有生产代码/API/schema/安全边界修改。

## 结论与交接

T035诊断交付完成，不等于T032性能验收完成。现在不值得立即付费跑完整20：
先修空白chunk发送风险及候选标点辅助识别，再确认首段严格规则可稳定评审；
正文token2秒仍有观测超标，画像串行有证据但改变顺序需要决定。
未来20样本计划仍需独立批准，基线若修复应重新明确冻结；本次3样本不得混入。
所有历史失败保留，无补跑、未push/merge/归档/进入MVP0.3。
