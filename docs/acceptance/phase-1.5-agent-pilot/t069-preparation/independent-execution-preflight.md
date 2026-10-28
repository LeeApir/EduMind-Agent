# T069 真实执行入口独立预审

评估者：`pilot_independent_evaluator`，身份 **assistant**。记录时间：2026-10-28T13:48:11+08:00。

结论：**暂不进入最终冻结、e03选样或真实执行。** 以下P1证据及核定门禁缺口应先修正，再提交新的准确候选供独立复审。本文件是预执行源码审阅，不是T069采集完成、T070效果评估、真实执行批准或生产开放。

## 范围与方法

只读审阅真实CLI、持久账本、wire校验、只读检查器、baseline-v2及相关测试源码。未运行任何引擎、模拟器、C、测试、DNS或HTTP；未读取凭据、e02私有真值/推导、开发种子或封存材料；未选择e03参数。只新增本审阅文档，不改源码、任务状态、执行日志或Git历史。

本次候选仍在开发，审阅期间CLI已增加路径及policy校验；以下按本节快照登记，不把早期已修正的路径问题作为当前缺陷。测试通过数来自开发方报告，本评估者没有重跑或将其计入独立验证。

| 文件 | SHA256 |
| --- | --- |
| `scripts/run_p15_agent_pilot.py` | `9d66b254e47274bb553aee7adb23e170bb55a37c9b725128adc3dc02245928be` |
| `scripts/isolated_diagnostics/p15_pilot_execution.py` | `4bfc6da3b76f2c124118b0d40dcd083d258822ac094d4109dc19ee3a04087051` |
| `scripts/isolated_diagnostics/p15_pilot_wire.py` | `7df1804195e7d20cb7fc2c4638257507210e8188ac4bcb28db68cc1d584d0dec` |
| `scripts/check_p15_pilot_execution.py` | `f28b6709d503895045327d222381c25c1de74a4a3c7e4b825211cbe3afafc92b` |
| `scripts/isolated_diagnostics/p15_pilot_baseline.py` | `f5ee4803d4456eeba23957f6bd9f79e87fdf7051737b4e700572dd943d86d1be` |
| `scripts/tests/test_p15_pilot_wire_execution.py` | `7885fa4c954862ec04cc7621fe0954f9146748fcc0db3a0353d5ef011e126102` |
| `scripts/tests/test_p15_pilot_baseline.py` | `d950833fb49b7e3b60b1d271bddb4d62429fbcabacb82de723ee47015976cb7c` |

## 需要修正的发现

### P1-01：独立真值核定未形成真实入口的完整门禁

位置：`scripts/run_p15_agent_pilot.py:61` 的 `read_inputs`；同文件 `grant_before_keys` 的materials检查。

目前读取路径、输入摘要和 `materials.status == independent_e03_ratified` 即可进入下一门禁，没有核验独立核定者姓名/assistant身份、核定时间、真值摘要、手算/核定摘要以及核定针对的准确候选。将状态字符串写成已核定，不能证明独立真值已存在且绑定当前代码/Prompt。冻结协议明确要求缺少独立真值签核姓名、时间、digest时拒绝真实入口。

建议：校验不含答案的独立公开核定材料，要求准确输入摘要、真值摘要、独立评估者身份/时间及候选核心/Prompt摘要全部匹配。公开核定材料应被准确执行manifest覆盖；无需也不应让开发者或模型读取私有真值。输入格式校验和核定来源校验应分别成立。

必要回归：已批准grant但缺核定摘要、核定身份错误、核定时间缺失、truth摘要缺失、输入/候选/Prompt任一摘要不符时，均在Key、DNS、输出目录创建前拒绝。

### P1-02：首版检查失败可因缺少issues而被最终accept掩盖

位置：`scripts/isolated_diagnostics/p15_pilot_execution.py:340` 至 `:382`，`Journal.accept_report`。

报告允许首版 `checks.facts`、`checks.answers` 或 `checks.code` 为false但 `issues=[]`；fatal只从issues的严重性/领域计算。若第二版与顶层checks全true且issues为空，则既满足最终一致性又不触发fatal，能够advance。首版已记录的事实/答案/代码失败因此可以没有证据映射就从最终成功中消失。

建议：拒绝检查结果与证据不一致的报告；每个false检查必须有明确范围、原因和准确原件证据，unknown也不能被空issues掩盖。首版事实/答案/代码安全失败应符合既定停止口径，不能靠省略issues对象绕过。普通教学修复的合法范围单独判定。

必要回归：首版facts/answers/code=false且issues为空、首版有严重证据但最终全true、首版unknown但最终accept、最终checks与逐版记录不一致，均不能advance；合法普通教学修复仍保留两版并可独立判定。

### P1-03：只读检查器未重验独立报告的完整有效性

位置：`scripts/check_p15_pilot_execution.py:336` 至 `:352`。

检查器只核对独立报告文件与账本事件相等、result摘要匹配、顶层accept及最终checks全true/最终issues空。它没有重验报告的评估者身份、包绑定、证据来源、全部版本覆盖、逐版证据指针、首版严重错误及最终/逐版一致性。结构自相矛盾的独立报告仍可能计入first/final成功，且返回 `evidence_verified=true`。运行时曾检查过不能替代只读证据复算。

建议：抽出不写账本的纯报告验证逻辑，由accept-report与checker共同使用；checker重验全部版本和原件证据，不调用模型或借其pass替代独立结论。报告身份仍是程序声明与职责约束，不能声称具备独立OS账户或密码学签名证明。

必要回归：对已保存报告删除一个version_review、改评估者/包、移除首版严重停止、改证据指针或最终一致性后，即使报告文件与对应事件保持一致，也须拒绝。测试应覆盖内部证据矛盾，而不只检查原始文件SHA变化。

### P1-04：检查器未把完整工作流绑定准确输入与协议因果关系

位置：`scripts/check_p15_pilot_execution.py:74`、`:271` 至 `:335`。

`validate_example(example)`只证明示例与它自己携带的spec一致，没有核对它等于inputs中该slot的准确spec。dispatch仅与其wire请求互相比较；未重验规划选择/coverage、各阶段输入由前一准确响应构造、审核source_digest/意见与准确候选的绑定、每版identity和父版本绑定。对于拒绝槽，只要state=refused且calls=0就计入正确拒绝，没有重新核对准确拒绝原因。

影响：槽标签保持不变而整套工作流属于另一份合法spec、生成请求带入额外参考事实、审核针对另一候选、错误拒绝原因等证据关联问题，可能未被检查器拒绝。自洽的文件/摘要链不能代替与冻结输入及角色权限的绑定。

建议：从manifest中的准确inputs摘要开始校验，逐槽绑定spec/问题/身份；按角色重建允许的请求payload，验证计划/内容/审核/修复的父子来源，验证所有artifact identity及模型审核意见，并重判本地拒绝的类别/原因。B生成与修复只允许固定SPEC语义及其既定输入，不能含engine或独立真值；C按既定权限读取参考。

必要回归：另一合法spec整套移植到同slot、错误plan覆盖、审核source摘要错绑、生成payload额外增加参考观察、修复父版本错绑、拒绝原因错误，均须被只读检查器拒绝。

### P2-01：存在版本不等于首次完整结构成功

位置：`scripts/check_p15_pilot_execution.py:257` 至 `:258`。

`result.versions`非空即累计initial_structure，但C在动作完整性失败时也会保留degraded版本。这样的失败候选不应计入“无需修复的完整候选结构通过”。

建议：依据首版完整结构/动作检查的实际事实计数，明确是否通过；保留degraded版本作为失败证据。增加有首版但动作缺失/退化的回归，分母保持10。

## 已见的合理边界与仍待批准事项

- CLI先核对包与准确grant，再读取inputs、创建输出或加载Key；`--check`和`--assessment`分支不加载凭据。导入的Gateway/Markdown模块未见导入时读取Key的路径。当前pending材料不等于执行批准。
- Journal的SQLite预约在出站前提交，状态非complete阻断重发；每槽阶段序列限制B4/C5，总预约最多90。HTTP关闭重试/重定向/环境代理，域名经既有目标策略校验并固定连接IP，TLS仍保留目标Host/SNI。发生出站/协议异常即unknown并停止，不将额度退回继续尝试。
- 固定窗口使用绝对开始/截止时间，角色调用和独立报告等待均未暂停时钟；单请求还受120秒限制。窗口过期后不能继续发送。最终包仍应明确过期时的停止记录/未运行口径，不能只看残留awaiting状态断言尚有时间。
- 模型pass后暂停为awaiting_assistant，需准确结果摘要的独立报告再推进下一臂/槽。单次普通教学修复仍由B/C原有限状态机控制，旧版本原件保留；但P1-02/P1-03尚未修正，不能声称首版严重错误已不可绕过。
- baseline-v2的生成和修复payload都附带固定SPEC全文，已补齐上一轮“只给变体名”的语义缺口。B生成未见加入engine输出/私有答案；B审核与C同审核标准且读取参考事实。B整候选修复与C仅内容修复、不同payload/动作格式复杂度、C读轨迹及固定B后C顺序都必须披露，不能归因于纯角色数量。
- wire对已知审核回显后缀、短summary和成对UUID只输出隔离观察，不把它们当指令已送达、身份或上游上下文已核实；raw响应仍保存在受控目录。把这些旧规则延伸到新入口是新的准确兼容范围，本预审不批准延伸。
- CLI的LIMITS将input/output token总额与fee_cap设为null，并要求新grant显式接受unbounded token/金额及未核账单风险。这不同于“已具有限token/金额上限”；90请求、8000单请求输出、请求字节及3小时仍不能证明账单封顶。费率、币种与例外均须在最终准确包中明确，新用户批准前不能套用历史例外。此项属于待批准方案，不在本次源码审阅中默认认可或代签。
- checker以SQLite只读连接和共享锁读取，明确输出T070未完成/无生产准入；没有模型调用。但P1-03/P1-04意味着当前 `evidence_verified` 的验证范围不足，不能据它声称证据已完整重算。

## 后续门禁与独立性

先修正发现并运行相称的离线故障/篡改回归，再提交准确源码、Prompt、wire、检查器和执行策略快照供独立复审；全链冻结后才选择全新e03。e02形成早于B/真实执行器冻结，只保留历史语义参考，不追认为正式B集。最终新执行包与真实预算仍需用户另行准确批准。

评估者随后只向开发者提供调度输入和公开核定摘要；真值/推导保持私有，不传给生成或审核模型。共享用户和文件系统意味着隔离依赖职责，不能宣称操作系统级互不可读。T069之后仍须完整独立T070效果评估；本文件不改变T038、catalog_only或任何发布/评分权限。
