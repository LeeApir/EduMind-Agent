# T069 p01 独立采集证据复核

评估者：`pilot_independent_evaluator`，身份 **assistant**，非human。复核日期：2026-10-28。

**采集合规复核：通过。实验结果：首个B请求因具体JSON Schema被服务拒绝而停止，没有模型课程产物；不能据此确认教学质量或方案有效。** 已独立读取授权、准确输入、原始请求/响应/状态、结果和账本，核对私有e03材料摘要，并重跑只读检查器。没有追加请求、重试、修复Schema、改样本或改冻结文件。

本报告仅复核T069是否按准确授权采集、保存、停止和报告。不是T070完成结论，也不是继续调用、费用扩张或生产准入批准。主执行者仍须按工作流完成T069交接及提交，再正式启动独立T070。

## 准确授权与材料

- 用户批准提交`1bd3228`对应ADR0042 A—C、准确包、合成外发、新窗口及费用例外。
- 执行manifest SHA256：`295bc335af529b6906a51a61c5e22586b414d4e6c9986068534703b7b0aebe0d`。本助手实际逐一核对其中41个文件，全部匹配。
- 执行输出：`/private/tmp/edumind-p15-agent-pilot-p01`，目录0700；所有现有文件0600。
- 输出`grant.json`与当前准确批准登记的解析JSON一致，规范JSON摘要相同；绑定上述package、T069范围、90请求上限、10800秒新窗口、120秒单请求、8000请求输出上限以及本次明确接受的无token/金额总额上限等例外。没有继承旧批余额。
- 窗口为2026-10-28 **16:17:33.990413至19:17:33.990413（Asia/Shanghai）**，截止不包含。全部现有receipt在此窗口内、时间非递减。
- 输出inputs SHA与独立e03公开核定相符；私有inputs/truth/ratification/推导的实际摘要均重新匹配公开登记。只由独立评估者读取私有内容，报告不公开参考答案。

初次自写辅助核对曾直接比较输出紧凑JSON与批准登记的原始字节，因序列化格式不同而断言失败；随后改按已冻结的解析JSON及规范摘要比较，确认一致。没有修改授权文件或证据来消除此差异，不把失败辅助断言当成候选通过证据。

## 唯一实际请求及允许材料

唯一ticket为`call-000`，槽`E03-S01`、臂B、阶段`pilot_baseline`。冻结来源及账本记录为生成目标`api.deepseek.com/responses`、请求模型别名`deepseek-flash`、reasoning=none、temperature=0.2、max_output_tokens=8000、stream=false、store=false，以及完整冻结严格Schema。记录为1次real transport，不是Mock结果。

实际生成payload的准确键集合只有：`semantics`、`spec`、`goals`、`question_keys`、`code_anchor`。本助手直接核对固定SPEC全文、该准确槽spec、四目标/四问题键及槽锚点一致；消息只有system/user两条。没有tools、previous_response_id或附加消息，没有引擎观察/答案/轨迹、独立truth/ratification/推导内容或无关学生/封存材料。B流程本地构造的引擎reference存在于受控result事件中，但没有进入该生成请求；这是审核前本地参考，不是模型产物或质量分子。

请求本身和完整Schema与冻结候选及只读Replay一致。本报告不为服务器错误改写Schema，也不推断具体哪个Schema节点导致兼容失败。

## 原始响应与停止事实

原始状态：**HTTP 400**。原始响应只有`error`，类型/代码均为`invalid_request_error`，message为：

> Invalid json schema: one of `type`, `anyOf`, `$ref` field is required (request_id: 609de88f-1b8d-42f5-9ce7-982321cfcb3d)

没有成功模型内容、usage或可信计费信息；没有候选versions、模型审核或修复。结果为`state=stopped`、`reason=HTTP_STATUS`、`calls=1`、`versions=[]`；工作流事件是example→dispatch→unknown→stopped。

账本的`unknown`表示没有可信模型完成/用量结算，并不表示没收到HTTP响应：400状态和219字节原始响应均已保存。调用表保持unknown、response_sha/usage为空；原始响应摘要仍由`wire_observed`事件绑定。没有settled事件、独立accept事件、pending调用或退款/次数复用。

| receipt | Asia/Shanghai时间 |
| --- | --- |
| started | 16:17:34.148262 |
| reserved | 16:18:09.126066 |
| target_pinned | 16:18:09.200783 |
| transport_kind=real | 16:18:09.225419 |
| sent | 16:18:09.226231 |
| wire_observed | 16:18:09.556470 |
| stopped（WIRE_UNKNOWN_OR_FAILURE） | 16:18:09.558850 |
| slot_result（stopped） | 16:18:09.568598 |
| stopped（HTTP_STATUS） | 16:18:09.570961 |

sent至wire_observed约0.330239秒、reserved至停止结果约0.442532秒，只是此次客户端拒绝响应/收尾间隔；没有教学首token/首段时延，不作为成功性能样本。两条stopped记录共同保留传输层和工作流原因，未重开批次或推进position。

## 实际只读复算

本助手实际以仅设置必要Python路径、禁写pyc且不带Provider环境凭据的子进程执行：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_agent_pilot.py --assessment
```

退出码0。输出确认：`evidence_verified=true`、`authority_pins_verified=true`、`recorded_window_verified=true`、`batch_state=stopped`，batch协议为`pilot-batch-protocol-v1`。独立复核了grant/input pin、receipt链、批次/调用投影、唯一出站、准确HTTP停止及固定分母；没有采用开发者或模型的pass结论替代这些检查。

检查器读取前后，输出目录所有文件SHA完全一致；未新增文件、修改账本或请求服务。本次独立复核新增Provider/DNS/HTTP调用为0；本批累计真实请求仍为1。检查器内部的纯抽象引擎仅复核既有参考/Replay，不用于生成或更新独立真值。

| 计数 | 结果 |
| --- | --- |
| 计划臂槽 | 28（B/C各10支持＋4拒绝） |
| 预约／真实HTTP响应 | 1／1 |
| unknown／pending | 1／0 |
| 已记录槽结果 | 1，首B停止 |
| 未运行臂槽 | 27（B剩余9支持、C全部10支持、B/C共8拒绝） |
| 首次完整结构 | B 0/10；C 0/10 |
| 首次端到端／最终端到端 | B均0/10；C均0/10 |
| 本批实际正确本地拒绝 | B 0/4；C 0/4，全部未运行 |
| 实际模型审核／修复 | 0／0 |

上述固定分母保留失败和未运行，不把未运行当错误回答，也不补充样本或用离线Mock成功补分。0/4仅是本批已观察正确拒绝数，不证明真实拒绝逻辑失败；拒绝槽根本没有运行。所有质量分子为0，不代表已经观察到内容错误或已经完成正式质量评估。

## 用量、费用及兼容/质量边界

- 服务未返回usage；输入/输出/推理token、缓存和计费token均未知。请求的8000上限不等于实际消耗，6790请求字节也不能转换为真实token账单。
- 实际费用、币种和账单未知，不能因400或缺usage写成零费用，也不能按公开参考费率补造账单。检查器actual_invoice/actual_currency为空，正确保留未知。
- 已确认：该冻结B完整Schema请求在此次生成端点被400拒绝，**具体Schema兼容没有通过**。未验证C规划/内容Schema、审核端点、修复路径或成功响应兼容；也不将本次失败推广为所有模型/Provider不支持。
- 没有模型课程正文/题目/答案/动作候选可评。教学质量、独立端到端成功、审核召回/误报、修复收益和多Agent相对效果均未测或证据不足。没有可比B/C成功对照，也没有稳定时延或质量提升结论。
- `clock_source_independently_attested=false`：复核证明记录时间数值与窗口一致，不是独立UTC或外部请求账单认证。服务别名、上游实际模型版本和隐藏上下文仍不能由本400独立确认。

批次停止不可逆；未用的请求上限不提供继续权限。不在此批调整Schema、重试、换模型、补样、恢复unknown或把未运行槽改为通过。后续如拟改变接口/Schema再验证，须另行形成准确方案和授权；本报告不代为启动。

## 原件摘要

以下相对于`/private/tmp/edumind-p15-agent-pilot-p01`，均已实际读取核对：

| 文件 | SHA256 |
| --- | --- |
| `grant.json` | `fa879baa205854062242a7908bcef5210c0c096d334f98b9760376df598ea29e` |
| `inputs.json` | `b95a46fdb7b438faa677fbbcb32ada52fd77e4a04ddd92717fe1072251256d98` |
| `call-000-request.json` | `abd06d9b3a7043bef7825f1915120ad92f73bc154f744d34bb1388e27977c69b` |
| `call-000-response.json` | `662956d5b2a2a0c4c259bda9f3f263789ff2fd6d195446c2de15f2d8c83723cd` |
| `call-000-status.json` | `99a5642d715711b7096d3777e06393b44c8cde2aedeacc717ec8948d9dd46648` |
| `slot-00-B-result.json` | `db5090b51b184d75c952fc4511e27cdd69a4964458b1c62213fbbfce38002dad` |
| `ledger.sqlite` | `76f27caca3741f06efca482978083170c309b5c85552a0df4ee629fb8401dc91` |

本次只新增此采集复核文档，冻结41文件和运行原件未改。T070仍须在正式领取后由独立助手对全量现有产物/缺失、冻结指标和采用建议作单独结论，不能因本报告采集合规而提前记为完成。T038、catalog_only、原教学标准、H封存及生产/评分权限保持。
