# 计划与混合审核独立执行包 r01

本包交付可实际执行的独立台账和执行器，**尚未激活，真实Provider调用0，5小时计时未启动**。已沿用并核验用户批准的[预算与16项独立预标签](../phase-1-plan-admission-authorization-r01/CURRENT-STATUS.md)，不重复申请59次额度、5小时或标签确认。具体执行代码与证据现由本包manifest绑定；启动本包需要一次明确的激活指令，随后生成绑定该manifest的activation.json。准备包、旧停止运行及其账本不改、不重开。

## 固定对象与限制

材料/Prompt/完整业务Schema/判据/配置来自[T085原冻结包](../phase-1-plan-admission-preparation-r01/README.md)，父manifest SHA-256为`b99c08f657b084c849b36163339fe0526f484b40d7f76a991d8e99cca7653303`。生成仍为DeepSeek `deepseek-flash / none`；审核仍为`https://www.cbbb.fun/v1`渠道的`gpt-6-luna / high`。新计划Schema真实渠道兼容仍未证明，P01是第一个兼容性及正确对照；失败即停止。

未改生产Prompt、Schema、生成服务或默认模型。固定审核16份完整实际Mock请求（4计划＋12单元）与父包出站正文逐份相等；独立生成后续请求使用本次真实上游，不复制Mock预期答案。所有材料属于开发回归，不能证明泛化或计入T040正式分母；H封存、T040 blocked，生产验证器白名单仍为空，本轮不尝试自动计划重建。

| 顺序 | 执行项 | 请求上限 |
| --- | --- | ---: |
| 1 | P01–P04计划检查 | 4 |
| 2 | 原12份固定审核各一次，再按预登记顺序重复8份正/错对照 | 20 |
| 3 | G01–G04各生成计划＋三资源，无审核/修正/DB/发布 | 16 |
| 4 | G03完整链，已选stack节点，映射0、重建0 | 正常9，最多19 |
| 合计 | 29项，每项之后人工核对 | **最多59** |

完整顺序及每项材料摘要在manifest.slots中；8次重复是事前登记的波动测量，不能重复直到通过。基础60中的1槽关闭，未用额度不能调换或补发。输出配置上限求和370688；输入量未知，费用不限。审核8192、计划2048、资源4096；单次最多60秒，每项/正式操作180秒，全局最多18000秒。完整链修正最多5对，每资源最多2对，仍受生产共享20次/180秒控制，本轮更严格上限19次。

## 台账、截止与停止

新运行只使用`local-materials/phase-1-plan-admission-execution-r01/run.sqlite`。显式activate且前置核验通过后才创建T0；准备、批准、DB迁移不启动时钟。T0永久保留，5小时包括人工等待；每次发请求及提交评分检查绝对截止，剩余不足60秒时调用超时同步收窄。到时未审/未运行项保留未完成，不追加新窗口。执行器按命令运行，没有后台唤醒或自动续跑。

每次先持久预约，再作出站及返回验证；预约后失败、未发送或发送状态不明均不退款。每项只能启动一次；崩溃留下running/reserved时禁止重放，需停止本轮并保留证据。CLI独占文件锁，SQLite事务串行保护额度；同一项尚未由Lee签核通过时，下一项不可开始。自动重试与回退为0。Schema、传输、模型/用量/参数、已知标签或路由不符立即停止；语义、附带误报、教学或引用经人工判断失败也首败停止。核心拒绝正确不抵消附带错误。

不会自动通过人工门。完成项先进入awaiting_human；GPT可以生成评分草稿，只有Lee实际核对并签署完整记录后才能推进。发现首败立即保留并结束该候选，不修改材料、Prompt或标签继续本轮。用户明确停止同样不可重开。

## 证据和评分

请求/回答只存于0700私密目录及0600不覆盖文件，不纳入Git。记录完整中立请求、实际无认证头出站字节、Host/SNI/固定公网IP、原始回答及有界解码信息、完整业务校验后的值/用量/传输审计。逐次重算适配器请求、解码回答和配置摘要；Schema投影后继续完整本地校验。默认真实工厂使用公网SSRF守卫、TLS、固定IP、无代理环境继承/重试；测试的固定IP与MockTransport只通过测试注入，CLI无切换开关。

不读取或记录认证头，冻结只记录.env权限及文件元信息。实际激活/执行时才用已有精确Key选择器读取原DeepSeek Key与Luna Key；不打印Key。原始和解码后各限制4MiB，适配器保留自己的更小上限；不安全编码、解压超限或Key反射的回答正文不保存，记录安全失败及摘要。HTTP/Schema失败保留安全原始证据，禁止自动重试。

沿用父包[evaluation.schema.json](../phase-1-plan-admission-preparation-r01/evaluation.schema.json)和[空模板](../phase-1-plan-admission-preparation-r01/evaluation-template.json)。每项的result.json作为统一证据根，包含material、result、calls、parsed_calls、logical_requests、review_sources及工件摘要。record中：

- `artifacts.request_sha256`为按发送顺序列出的calls.logical_request_sha256数组的canonical JSON摘要；`response_sha256`为同序calls.parsed_sha256数组摘要。单次实际线缆/原始回答摘要另在calls及receipt中保存，不能把逻辑请求或聚合摘要冒称原始字节摘要。
- 每个模型回答的非空文本字段都须出现在某条claims.evidence_pointers中，例如`/parsed_calls/0/value/findings/0/impact`；一个字段内的多个断言须人工拆分，不因字段枚举完整就声称语义完整。代码、计划、未决及附带建议也要核对；coverage.checked等枚举只是记录声明，不是正确性证明。
- 每个模型实际引用的锚点须列入citations，anchor_id使用`调用序号:原锚点ID`（如`1:p3`）。source_pointer须为`/review_sources/1:p3/source_text`；该文本由本次请求锚点的实际字段及UTF-8区间提取，不能借邻近字段作证。quoted_source必须真实存在于该字段，supports_claim_ids须指向已登记断言。
- 完整性、严重错误检出、附带错误、教学覆盖、引用及标签匹配分开登记。Schema只检查一致性、清单与摘要，不证明人工实际阅读或语义为真。完整拒绝正确但附带建议错误：严重检出可pass，incidental_falsehoods=present，quality_success=false，停止。
- 正/负审核对照按冻结标签计分；教学缺口样本正确转人工可以属于诊断通过，不能算产品自动发布成功。生成草稿通过须教学覆盖pass；完整链通过还须实际自动完成、隔离发布及全部历史核对。所有记录`eligible_for_T040_denominator=false`，人工通过不补自动成功分子。

## 完整链隔离和输入绑定

仅允许专用容器`edumind-phase1-t037-pg`的127.0.0.1:15437、数据库`edumind_catalog_plan_admission_r01`，已迁移至0033并验证空白。激活和完整链开始前再次校验库名、迁移及空白用户；不能从环境选择生产库。实际创建新owner/operation/unit/plan，保存新绑定及全部计划、前置检查、审核、候选资源、修正许可/发送记录、人工案件完整历史和隔离发布证据；网络/Schema/计划转人工后的已持久证据同样保留。

G03原文与已选stack节点不变；这不是重新跑HTTP目标解析/画像/路径集成验收，也不新增映射请求。生产服务在原PlanInputs快照外增加已有`reference_context`字段，执行器只允许这一精确的已存在变换，保存original_snapshot、permitted_snapshot_addition及actual_snapshots供逐项比对。其他目标、节点、输入、策略变动即失败。旧候选不复用，不执行生成代码，不发布生产内容。测试进程的dynamic仅用于隔离读取检查，随后恢复环境；不改变服务器默认catalog_only。

## 命令及当前验证

离线检查（不读Key、不调用Provider）：

```sh
backend/.venv/bin/python scripts/run_plan_admission.py check
```

准备DB使用`prepare-db`，只操作白名单隔离库；已经完成，不能在激活后再次准备。`freeze`只可写一次；本包已冻结后不能覆盖。新源码、配置、Schema、材料或.env元信息变化会阻止运行，需要新包保留原证据。原包与H/旧四账本摘要检查继续生效。

获得对本具体manifest的启动指令后，另存activation.json（decision=`activate_plan_admission_execution_r01`、manifest_sha256、reviewer=`Lee`、实际source_user_message），然后依次：

```sh
backend/.venv/bin/python scripts/run_plan_admission.py activate
backend/.venv/bin/python scripts/run_plan_admission.py run --slot plan_review:P01:1
backend/.venv/bin/python scripts/run_plan_admission.py report
# Lee实际核对评分后：
backend/.venv/bin/python scripts/run_plan_admission.py assess --slot plan_review:P01:1 --evaluation /absolute/private/evaluation.json
# 只有通过才可以开始P02；首次失败立即停止，不能补发。
```

`stop`明确停止；`report`只显示台账及摘要，不输出课程正文、Key或DSN。尚无activation.json与真实run.sqlite。离线回归、三条实际隔离PG路径及保留的早期失败见[validation.json](validation.json)、[offline-tests.json](offline-tests.json)及[pg-integration.json](pg-integration.json)。Mock完成/人工门测试中的预设pass只是机制夹具，不是本轮真实成绩或代签实际输出。
