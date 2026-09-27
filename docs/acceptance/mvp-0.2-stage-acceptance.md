# MVP 0.2 阶段验收（通过，含历史失败记录）

日期：2026-09-26。执行人：Lee。任务：MVP-0.2-T025。

## 结论

最终结论（2026-09-27 10:56）：MVP 0.2 阶段退出验收通过。
当前模型deepseek-v4-pro-0813、Responses传输，资源指令v8/审核指令v2；
画像提取及行为更新指令v2仅重申原字段契约，schema、白名单、保守降级和验收阈值不变。

- 质量v11：完整86次无重试，结构60/60、题型20/20、严重19/20、模型语义15/16达门槛。
  前置方向漏检一例，正确删除对照TIMEOUT，对照9/10，仍按原口径计失败；没有挑样本改计分。
- 画像诊断v1：3次无重试，初始提取未降级、两次行为更新均合法无变化，不伪造更新。
- 真实闭环v10：10次实际尝试、公开题面独立B/T/B，三类正式资源审核发布；两次score1，
  mastery0→.55→.9515/mastered，画像两次no_change，推荐linked-list-concept/path v2及前置理由。
  TestClient路径每接口100样本+5预热，读取P99 35.175ms、重规划P95 47.43ms、失败0。
  本机独立TCP HTTP路径证据仍见mvp-0.2-path-performance.json，不把TestClient冒充HTTP。
- 最终后端388测试无跳过/7既有警告，Ruff/Mypy55源文件通过；前端55测试、类型检查/构建
  通过，lint0错误/67样式警告。浏览器route-mock E2E通过，console仍有401/404；
  webapp-testing技能用于生命周期及交互复核，不替代真实Provider闭环或宣称浏览器无错误。
- 当前镜像manifest3a88d834d2719030ddecb95d29b7a9e6ea10a9e57cb95eaa52b86e9a5b369700，
  隔离项目edumind-mvp02-acceptance，0009 head，seed→restart postgres/api→check恢复通过，
  合成资源10f7dcdc-6985-47f9-af20-51bbbdaefc84；测试卷保留，零模型调用。
- 本轮13请求（画像3/闭环10），T025验收累计901，用户连通测试另12；金额/余额未知。
  全部旧失败证据保留，不用于替代当前通过组合。没有修改真实.env或自动切换模型。

限制：小图谱、单并发、本机预热结果不证明公网或高并发容量；两次同题满分仅验证既定
掌握度规则，不证明学习效果。31550ms是完整资源生成时长，不是首段P95。
当前Pro首段P95未单独测量，MVP0.1历史证据不能推断换模型后的该指标；本任务按MVP0.2
闭环/路径/正式资源质量退出范围结题，不宣称达到全部后续产品发布指标。
保持默认Responses，Beta仍仅显式同源可选且完整质量失败记录保留。
本阶段所有任务完成后停止，不自动push、merge或创建MVP0.3活动任务。

最终命令：

```text
backend: uv run --env-file ../.env python ../docs/acceptance/diagnose_profile_contract.py --confirm-billable --output ../docs/acceptance/mvp-0.2-profile-diagnostic-v1.json
backend: EDUMIND_DATABASE_URL=<isolated test DB> uv run --env-file ../.env python ../docs/acceptance/run_mvp02_acceptance.py --confirm-billable --output ../docs/acceptance/mvp-0.2-stage-report-v10.json
backend: EDUMIND_TEST_DATABASE_URL=<isolated test DB> uv run pytest -q
backend: uv run ruff check app tests; uv run mypy app
root: pnpm --dir web test; pnpm --dir web lint; pnpm --dir web build
backend: uv run python ../web/tests/e2e/run.py
root: docker compose --env-file /dev/null -p edumind-mvp02-acceptance build api
root: docker compose --env-file /dev/null -p edumind-mvp02-acceptance up -d --no-build api
root: docker compose --env-file /dev/null -p edumind-mvp02-acceptance exec -T api uv run alembic current
root: docker compose --env-file /dev/null -p edumind-mvp02-acceptance exec -T api uv run python tests/compose_recovery_check.py seed
root: docker compose --env-file /dev/null -p edumind-mvp02-acceptance restart postgres api
root: docker compose --env-file /dev/null -p edumind-mvp02-acceptance exec -T api uv run python tests/compose_recovery_check.py check
```

## 历史过程（以下失败结论不代表最终状态）

最新（2026-09-27）：用户确认审核分类修复，审核指令v2明确执行/内存安全风险归code_safety，
业务schema、错误集、评分与阈值不变。三次定向诊断9.43秒，两个安全错误正确拒绝并分类、
正确对照通过；不作为完整质量证据。完整质量v11共86请求548.82秒，结构60/60、题型20/20、
严重19/20=95%、模型语义15/16=93.75%，通过原门槛。审核明细人工核对：
list-prerequisite-direction漏检；correct-deletion审核TIMEOUT按失败，对照9/10，未重试或改计分。
其余检出问题有具体说明；不能把质量通过理解为100%可靠。

当前Pro真实闭环v9共10请求失败：三类资源审核发布，按公开题面独立B/T/B作答，两次score1，
掌握度0→.55→.9515/mastered。初始画像提取及第二次行为画像更新均additionalProperties；
初始画像按既定保守策略降级，第二次更新profile_update_status=provider_failed使验收断言失败。
旧画像未覆盖，推荐和本轮路径测量未执行，不能用Flash闭环补证。生成总时长39300ms不是首段时延。
失败分类只有固定schema关键词，未保存模型原文，不能推测具体额外字段名称。
建议明确ProfileAgent输出字段契约后定向验证，需用户确认；不截取JSON、补造字段或降低校验。
388后端测试通过/7既有警告，Ruff/Mypy55/diff通过。初次uv缓存受限改临时缓存，
新增测试长行lint错误已修；全量387之后新增计分回归，最终全量388通过。
当前镜像构建manifest dec994272db06f0900aabe61b641cdbc8f870f486be50e539e9644c34423c128，
尚未用该镜像重启恢复，此前67b4548镜像恢复记录仅属历史证据。
本轮99调用（诊断3/质量86/闭环10），T025验收累计888，连通另12，金额余额未知。
报告：`mvp-0.2-safety-review-diagnostic-v1.json`、`mvp-0.2-resource-quality-provider-v11.json`、
`mvp-0.2-stage-report-v9.json`；未创建完成提交。

此前（2026-09-27 09:53）：用户切为deepseek-v4-pro-0813后，3次连通测试通过；
完整质量v10共86请求493.11秒，结构59/60=98.33%、题型20/20、严重18/20=90%、
对照10/10；模型语义14/16=87.5%低于90%，stage_gate_passed=false。
队列讲解第二份EXTRA_DATA/OTHER_SUFFIX，输出913 token、1消息1块，未到4096上限。
list-traversal-stop及list-delete-head均正确拒绝并说明NULL解引用/悬空指针风险，
但严重问题归类fact，基准要求code_safety，因此按原口径未检出，不改指标或覆盖报告。
当前Pro真实闭环未运行，不用Flash闭环补证。建议定向明确审核分类规则，需用户确认。
后端386项通过/7既有警告，Ruff/Mypy55/diff通过；本轮89次实际请求（质量86、连通3），
T025质量与闭环验收累计789，连通另12；费用与余额未知，无配额错误，不创建完成提交。
新证据：`mvp-0.2-resource-quality-provider-v10.json`、`mvp-0.2-pro-connectivity-v1.json`。

此前（2026-09-27 02:09）：deepseek-flash真实学习闭环、路径性能、题型与审核通过；
完整质量v9的schema58/60=96.67%低于98%，因此MVP 0.2尚未退出。
下文初始评分失败为历史排查记录，不能混同最新结论。
不能把 T024 的 mock 闭环或 T023 的资源质量报告替代本阶段真实闭环。

用户切回后的证据：

- 完整质量v8（86请求161.84秒）：schema59/60、严重19/20、语义15/16、对照10/10，
  但题型17/20失败。3请求新格式诊断复现两份删除填空无____/非整数答案，不倒推旧样本。
- 资源指令v8按PRD约3道客观题约束明确无需凑齐三类题型，概念/指针操作优先单选/判断；
  保留合法整数填空、旧指令格式门禁、原schema及评分规则，新3请求诊断通过。
- 完整质量v9（86请求167.02秒）：题型20/20、严重20/20、语义16/16、对照10/10；
  schema58/60失败，循环队列代码缺字段、栈讲解多字段。没有降低门槛或修剪输出。
- 当前指令v8/审核指令v1真实闭环报告v8：10请求通过，公开题面独立B/T/B作答，
  两次不同幂等键提交score1，mastery0→.55→.9515/mastered，推荐linked-list-concept/path v2。
  画像no_change未伪造。TestClient每接口100样本+5预热，读取P99 44.11ms/重规划P95
  48.033ms/失败0；非原生浏览器/独立HTTP/首段延迟证据，12.597秒生成总时长不是首段时延。
- 386后端无跳过/7既有警告、Ruff/Mypy55源文件/diff通过；浏览器route-mock再通过，
  console有401/404，不能声称无错误真实Provider浏览器。webapp-testing用于生命周期及交互复核。
- 最终Compose镜像manifest67b454830507871ee5cda78dcadb1e6bfe9889869a6b68e33662b71f6b838b6d，
  隔离edumind-mvp02-acceptance的0009 head、seed、restart postgres/api、check均通过；
  合成资源a2f5ddb3-efe6-4a96-8b94-17c82e9f640d恢复，0模型调用，不覆盖真实闭环证据。
- 此前已批Beta兼容范围内同官方主机隔离5请求仅4/5，C指针讲解JSON delimiter失败；
  真实.env/生产默认未改变，不将探针当完整质量通过。切回后新增193请求，T025验收
  累计703，另用户连通探针9次独立计账；费用/余额未知，持续必要计费授权仍有效。

剩余决策：是否评估另一模型或可靠严格结构化策略；不能盲重跑挑中通过报告、
补造字段/截取首JSON/降阈值或提前开发P1模型设置，当前任务没有完成提交。

最新进展（2026-09-27）：用户授权此key后续必要验证直到用量耗尽，无需逐次计费确认，
不扩大产品范围、不自动换Provider/模型。完整质量v7实际模型是deepseek-v4-flash-0731，
不是开始时预计的deepseek-v4.1-flash；报告保存实际配置与返回模型，不覆盖用户.env。
86请求496.72秒，结构46/60、客观题型19/20；26次模型审核全不可用，严重4/20仅来自
本地安全检查、语义0/16、对照0/10，阶段失败。
审核23次多余字段/2缺字段/1语法错误；生成14次讲解EXTRA_DATA/OTHER_SUFFIX。
补齐审核指令v1明确字段及schema后，3请求诊断两个错误拒绝、正确对照通过（7.3秒）。
另3请求公开讲解字符类别诊断一通过、两份尾随仅关闭大括号，见
`mvp-0.2-closing-delimiter-diagnostic-v1.json`，不能倒推全部旧错误同因。
资源指令v7对讲解嵌套关闭边界做定向约束，schema/解析门槛不变；106针对性测试通过。
后续真实质量与闭环尚待验证，不能把上述诊断当阶段通过。

资源指令v7定向修复后5请求47.6秒，仅2/5通过，3份讲解仍EXTRA_DATA；没有盲重跑完整基准。
该诊断报告误标structured_transport=mock，实际运行命令显式指定responses_json_schema；
元数据生成器已修复，原报告保留不覆盖。最终383后端测试无跳过通过/7既有警告，
55前端测试通过、Ruff/Mypy55文件/前端构建/diff通过；前端lint无错误、67样式警告。
本轮新增97真实调用，T025验收累计510，另用户连通探针9次（6失败/3成功）单独计账，
货币费用和剩余额度未知，未出现配额错误。计费授权不是当前阻塞；需当前服务商公开
协议文档或决定其严格结构化接口适配策略，不能截取JSON/降低门槛冒充通过。

## 真实闭环

入口：`run_mvp02_acceptance.py`，必须显式传入 `--confirm-billable`。
运行于 backend，使用 `uv run --env-file ../.env python ../docs/acceptance/run_mvp02_acceptance.py`，
提供 `--output` 新文件路径；`EDUMIND_DATABASE_URL` 指向隔离测试 PostgreSQL。
最多 30 次模型尝试，包括 Gateway 的重试；不切换厂商，不导出凭据或会话令牌。

保留三轮报告：v1/v2 前置断言失败，模型请求均为 0（报告未记录细分断言位置，
不推测其全部原因）；v3 使用明确的单链表目标，通过真实 Provider 生成并审核发布
C 指针前置知识的讲解、代码和三道练习，共 9 次模型请求，返回模型 deepseek-flash。
生成至公开题面约 16.111 秒。这不是 SSE 首段延迟测量，不能用于首段性能结论。

三道题要求解释 C 指针赋值、别名，以及链表 next 结构。执行者仅看到公开题面后
独立输入答案，没有读取答案键。作答要点分别为：a=20、p 保存 a 地址；p/q 均指向
a，赋值后 a=30、b=2；next 保存后继结点地址，以地址链接不连续结点。

验收断言失败后，通过只读 SQL 核对最新 `quiz_attempt` 的去敏评分摘要：

```json
{"created_at":"2026-09-26T09:49:35.00042+00:00","node_id":"c-pointer",
 "rule_version":"quiz-exact-text-v1","score":0.0,"correct_count":0,"question_count":3}
```

代码 `backend/app/services/quiz_scoring.py` 使用 NFKC、大小写和空白规范化后的全文
相等比较，不支持语义等价解释答案。生成指令 v3 没有限制练习为客观、唯一答案题。
因此开放解释题与已采用的确定性评分规则不相容。此问题会导致正确学生答案被判错，
影响掌握度和推荐；不可通过复制标准答案、写入虚假掌握度或降低验收断言过关。
旧 v3 报告未保存失败回执，本条 SQL 补充证据不冒充原报告字段。入口现已改为在
后续断言之前保留去敏回执，但不覆盖历史报告。

## 路径性能

命令：启动隔离 DB 的本机 Uvicorn 8001（不加载 Provider 凭据），随后从 backend
运行 `uv run python ../docs/acceptance/run_path_benchmark.py --output ../docs/acceptance/mvp-0.2-path-performance.json`，
同样设置 `EDUMIND_DATABASE_URL`。基准不调用模型。

环境：macOS 15.6.1 arm64、Python 3.11.16、真实 TCP HTTP→Uvicorn→PostgreSQL，
单并发、每接口 5 次预热后 100 次样本。独立匿名用户、合成初始画像、真实 10 节点
版本化 YAML。没有使用成功的真实测验画像，因此是独立性能证据，不是闭环通过证据。
原始延迟、最大值、P95/P99 和失败率保存在 JSON 报告。

| 指标 | 实测 | PRD 门槛 | 结论 |
| --- | --- | --- | --- |
| 路径读取 P99 | 35.067ms | 普通查询 ≤200ms | 通过 |
| 路径重规划 P95 | 47.877ms | 路径规划 ≤200ms | 通过 |
| 请求失败率 | 两接口均 0/100 | 本次要求无失败 | 通过 |

本机低并发、小图谱和预热结果不推断公网、冷启动或高并发容量。

## 退出清单与待决定事项

### 2026-09-26 用户确认后的修复与复测

用户已确认客观唯一答案约束。任务恢复，不再等待题型决策。生成指令 v4/v5/v6
与审核 v3 保持 schema-v1 和 quiz-exact-text-v1 不变；新增本地发布前题型检查，
格式不合格进入至多两次定向修正，仍失败则拒绝。单选事实正确性/唯一选项仍由
独立 ReviewAgent 检查，不把本地正则当作知识判断。v4–v6 资源均受本地门禁约束，
v3 和更早旧资源不覆盖。前端仅修复选项换行和窄屏折行，不向浏览器泄漏答案键。

- v4 质量：86 请求、267.88 秒，schema60/60，客观格式20/20，严重19/20、
  模型语义15/16、对照10/10；`list-insert-links` 审核不可用按未检出计数，不伪称成功。
- 真实流程 v4：7 请求，DB 显示缺失代码资源、生成失败1；入口当时没有细分错误码，
  不声称已知具体失败字段。失败报告保留。
- 真实流程 v5：8 请求，生成三类资源，但独立审核发现地址概念题被强塞整数答案，
  拒绝练习，未发布单元；不将此审核拒绝冒充通过。
- 指令 v5 增加整数题必须有已知条件下的可计算数值。真实流程报告 v6：10 请求，
  操作者按公开题面独立作答 B/T/1012（1000+3×4），两次独立幂等键提交同一练习，
  每次score=1，mastery 0→0.55→0.9515/mastered，路径v1→v2，推荐 linked-list-concept。
  重复作答仅用于验证既定阈值规则，不代表一般学习效果；ProfileAgent 返回 no_change，
  未为了演示成功伪造画像更新。
- v5 质量：86 请求、206.97 秒，schema58/60=96.67% 未达98%；代码失败分别为
  required 缺失、JSON EXTRA_DATA。客观题格式12/20不通过。严重/模型语义/对照均100%。
  该失败不被前一轮通过覆盖。
- 3 请求格式探针：三份新整数题均漏字面 `____` 填空位；摘要见
  `mvp-0.2-objective-format-diagnostic.json`。不能推定旧八份失败全部同因。
- 指令 v6 增加完整代码和客观题 JSON 序列化示例，并明确无 `____` 的整数问答
  不符合当前填空合同；严格 schema、解析和质量阈值不变。
- 当前 v6 质量：86请求、196.86秒；schema58/60=96.67%仍未达98%，客观格式19/20
  未达100%；严重20/20、模型语义16/16、对照10/10。失败是stack代码required缺失、
  array讲解JSON EXTRA_DATA，以及linked-list-deletion一份练习格式不合格；
  后者原始内容未保留，不臆测具体格式原因。报告为resource-quality-provider-v6.json。
- 当前指令v6真实流程报告v7通过：10请求，独立作答后两次score=1，最终mastery=.9515，
  mastered并推荐linked-list-concept；TestClient读取P99 31.014ms、重规划P95 46.458ms，
  各100样本/5预热/失败0。这不覆盖质量失败，也不冒充真实浏览器证据。
- 两轮实质不同提示修复后停止继续盲改。只读检查发现Responses适配器json_schema请求
  没有strict:true，属于待验证线索而非已证实根因；当前Provider兼容性未知。
  等待批准转向Provider结构化约束排查，不更换模型、不降低门槛、不放宽解析。
- 用户随后批准严格模式排查。隔离探针3请求、无重试：默认请求满足schema；
  strict=true第一次满足schema，第二次违反enum并被本地校验拒绝。报告
  `mvp-0.2-strict-probe-v1.json`。生产适配器未修改；反例排除“单加strict即可保证修复”，
  不能据小样本猜测远端内部机制。官方Beta严格工具调用属于另一接口策略，尚未获准切换。
- 用户再批准Beta验证：原schema探针2请求，enum通过但讲解400；常量等价投影后
  v2四请求全通过。加入显式服务端beta_tools选项，默认/真实.env未改变，不执行工具，
  普通文本与SSE不变，安全边界见PROVIDERS.md。
- Beta完整质量v1：86请求、299.52秒，schema55/60=91.67%、客观17/20=85%；
  严重4/20、模型语义0/16、对照0/10。26项模型审核均不可用，不能当作成功检出；
  生成失败为3个TIMEOUT、1个required缺失、1个UNTERMINATED_STRING，门禁未通过。
- 审核enum缺type的等价映射随后修正，1次审核schema诊断符合原schema；这只证明协议
  兼容，不覆盖原26项语义质量。当前没有Beta完整通过证据，不再盲改提示或计费重跑。
  需用户决定是否扩展到模型/Provider能力评估，不能静默更换模型或降低阈值。
- 用户选择不提前P1模型选择，随后批准先非计费诊断再本地修复。合成合法单选题含
  “为什么”被全局关键词误拒的代码问题已修复；仍拒绝解释要求、开放题和多答案，
  不能反推旧三份格式失败的具体原因。基准从2048对齐生产既有4096上限，门槛不变。
  新诊断保留固定结束类别/合法用量及审核失败尝试，不保存生成正文或原始供应商消息。
- 修复后93项针对性、361项全量后端测试无跳过通过（全量7既有警告），Ruff/Mypy55
  文件通过；离线质量报告`mvp-0.2-resource-quality-offline-local-fix.json`为30夹具schema
  通过/4本地安全错误检出/0Provider请求，16语义错误未评估，stage_gate_passed仍false。
  本轮未改前端、默认传输、模型或真实.env；本轮0计费，未进行真实质量复验。

本地最终回归：326 后端测试无跳过（7既有弃用警告）、55前端测试通过，Ruff与
Mypy54源文件通过，Web构建通过；浏览器路由mock回归含选项pre-wrap、390px无横向
溢出，桌面/移动截图已人工检查。前端lint为0错误、67既有警告，不声称零警告。
独立Compose修复中期v5镜像 seed/restart/check 成功；当前v6未重建验证。
数据库卷保留，未加载真实Provider凭据。
Beta开发中期镜像另已重建并seed/restart/check通过，resource_id为
`32312527-6438-4dbe-8e88-0683615ae7c1`；此镜像在最终enum投影修正前，不能当作最终Beta验收。
最终enum投影修正后本地全量349项后端测试通过、无跳过，7既有弃用警告；
Ruff及Mypy55源文件通过。前端仍为此前55项通过证据，Beta修复未再修改UI。
这一最终本地证据与中期Compose镜像明确分开。

原未通过阶段报告描述以下初始阻塞；它不代表用户确认后仍在等待同一决策。

- 知识结构、画像、证据/评分、掌握度、推荐、审核、UI 的自动化测试见 T001–T024
  各完成提交及 `mvp-0.2-closed-loop.md`；T024 全量 304 测试通过。
- 正式资源质量门槛见 `mvp-0.2-resource-quality.md`，v3 的 60 样本 schema 门槛通过。
- 真实“输入→学习→练习→掌握度更新→下一步推荐”未通过；没有完整阶段通过证据。
- 推荐修复：保持 ADR-0003 确定性评分，约束计分练习为选择/判断/唯一答案填空，
  增加生成和审核约束及回归测试，版本化新指令，重新执行质量门槛及真实闭环。
- 改用 LLM 语义判分会改变已批准的 ADR 与成本/可靠性边界，不建议为 MVP 0.2
  直接采取该方案。题型约束也需要同步任务修复范围，等待用户确认后实施。

修复后六请求诊断见 `mvp-0.2-resource-repair-diagnostic-v1.json`：
当前模型 `deepseek-flash`、默认 Responses 传输、4096 输出预算、无重试，15.79秒。
结构5/6通过，删除/插入/单链表三组练习题型均通过；数组讲解仍为
`STRUCTURED_JSON_INVALID / EXTRA_DATA`，输出1086 token，未达到4096上限。
诊断没有审核样本，不替代完整质量基准，阶段仍未通过。六请求批准额度已用完。

随后获准的非计费修复补充消息数/文本块数诊断，质量尝试账本仅输出验证后的数字。
拆成多个文本块的单个合法JSON仍通过；两个JSON拼接仍拒绝为EXTRA_DATA，
不提取首个JSON、不放宽schema、不记录原文。全量371后端测试通过（无跳过，7既有警告），
Ruff/Mypy55文件及diff检查通过，新增0真实请求。历史报告没有块数量，不能倒推失败来源。

数组讲解三请求诊断见 `mvp-0.2-array-diagnostic-v1.json`：12.02秒，结构2/3。
三次均为1条assistant消息、1个output_text块；失败EXTRA_DATA输出897/4096token。
本次失败不来自多块拼接或输出额度耗尽，额外内容已在单个文本块中；
不据此猜测额外内容类型或厂商内部根因。64针对性测试/Ruff/Mypy55/diff通过。
三请求批准额度已用完，未重试，阶段仍未通过。

随后获准的非计费诊断增加固定尾随内容类别：JSON_VALUE_SUFFIX（尾随完整JSON值）、
JSON_LIKE_SUFFIX（以对象/数组起始但非单个完整JSON）、MARKDOWN_FENCE_SUFFIX、OTHER_SUFFIX。
仅EXTRA_DATA错误可携带该枚举，报告不保存原文/解析位置，所有额外内容仍拒绝，
不恢复第一个JSON、不放宽schema。381后端测试通过（无跳过，7既有警告），
Ruff/Mypy55文件/diff通过，新增0真实请求；历史报告不能补造分类。

2026-09-27获跨日明确批准的数组诊断v2见 `mvp-0.2-array-diagnostic-v2.json`：
3请求12.12秒，结构3/3，均1消息/1块，无重试；未复现EXTRA_DATA，无新尾随类别证据。
73针对性测试/diff通过。该小样本不能证明已修复，完整质量基准尚未重跑。
本日3请求额度已用完，当前建议为另行批准最多86次完整基准，不自动执行。

初始失败闭环9次；T025至当前累计413次真实请求（闭环44、质量344、格式探针3、strict探针3、
Beta协议探针6、审核schema诊断1、修复后诊断6、数组诊断6），
货币费用以 Provider 账单为准；当天统一授权不等于放弃 ADR
和阶段退出标准。不 push、merge、跨入 MVP 0.3；当前成果保留待修复。

## 2026-09-27 收尾批准追加（不覆盖上述历史）

用户明确批准独立教学首token≤2秒保留未通过证据、转后续优化，不再阻塞MVP0.2收尾。
PRD学习闭环退出验收通过；T032据批准后的范围结题，不表示旧冻结综合gate通过。
T038 Flash正式20样本HTTP首字节P95 1.647秒、可学习首段3.094秒达PRD；
独立validated教学token2.633秒仍未通过，原始audit=false及全部历史失败证据不变。
内部模型尝试失败1/161，用户操作失败0/20，不能混算。
T025/T031 Pro闭环/质量与T038 Flash性能分列，不宣称Flash重新完成全部闭环/质量验收。
批准记录、原始文件SHA、范围与后续优化交接见[mvp-0.2-closeout-decision.md](mvp-0.2-closeout-decision.md)。
仅本地治理提交；不自动归档/进入MVP0.3，不push/merge，不追加计费复测。
