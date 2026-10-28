# T069 头插协作对照执行包 p01（待批准）

状态：pending。T071已独立复审通过并完成393b9f1，历史[阻塞决定](../t069-preparation/BLOCKED-DECISION.md)保留。全量候选36文件冻结后，独立助手已完成新e03的10支持+4拒绝槽手算核定，公开摘要见independent-e03-summary.json，准确绑定见materials.json。此包待用户准确批准，不是执行授权。具体决定见[ADR0042](../../../ADR/0042-pilot-controlled-execution.md)，原职责见已批准ADR0041。

## 候选与范围

仅隔离头插法，10个支持槽+4个本地拒绝槽，B/C交错共28臂槽。B一次生成全部代码/题目/参考答案/动作，C规划选择→确定性示例→内容→程序动作；两者按同一原教学标准审核，普通教学问题最多一次修复。B修完整候选、C只修内容，差异公开。支持B最多4请求、C最多5，总计≤90模型HTTP（生成模型≤50，审核模型≤40）；拒绝槽0请求。没有额外计数、/models或兼容probe；首个实际请求若接口/具体Schema失败即全批停止，不额外补发。

模型与准确端点固定于policy.json：DeepSeek官方deepseek-flash/none生成，AIAPI gpt-6.1-sol/low审核。别名回显不证明内部模型快照、完整上游上下文或教学质量。请求temperature=0.2、max_output_tokens=8000、stream/store=false、strict完整Schema，单请求≤120秒，输入/响应字节边界131072/2097152。服务是否接受这些具体Schema尚未真实验证，任何异常即停。

新窗口登记起10800秒含全部独立复核等待。拟申请token/金额总预算均不限；客户端取消后可能继续计费、中转真实硬限与上下文/留存无法独立证明。rates.json保存2026-10-28的公开标价：DeepSeek[官方价格页](https://api-docs.deepseek.com/quick_start/pricing/)和AIAPI[公开页面](https://aiapi.world/docs)。页面以$展示，实际账户币种、费率、推理/缓存及隐藏上下文计费未独立核实；不据此伪造实际账单或宣称货币硬上限，不继承旧费用例外。

## 材料隔离与独立核定

用户已指定所有内容由助手复核，并明确授权独立子助手；核定身份assistant，不记human。e01问题、e02参考及其局限保留；e02在全链冻结前产生，不作正式样本。候选代码/Prompt/执行器/政策冻结candidate-manifest后，独立助手才选新的e03参数、手算参考及动作/题意核对规则，公开核定摘要绑定姓名/类型/时间/候选及材料SHA。开发侧与模型均不读取独立真值，仅开发侧读取调度inputs。

真实入口校验核定摘要、冻结时间、候选/输入绑定、10支持的五类各2槽及四类拒绝各1；私有材料须0700目录/0600文件。私有真值的摘要由独立助手登记并在复核时验证，执行器不读取真值内容；同一用户与文件系统下的职责隔离不等于OS级隔离或密码学身份认证。仅外发本批合成规格/目标/固定语义/轨迹/模型候选及必要审核/修复上下文，不外发独立真值、真实学生、旧签核课程或H。

每个模型审核通过槽暂停，独立助手实际复核全部版本并写报告后才能进入下一槽。报告应包含准确包/slot/arm/result摘要、逐版本的事实/答案/代码/动作/教学检查和问题到原件的定位，证据精确匹配。检查失败不得缺少证据；首版事实/答案/代码失败或严重问题不能被后续版本抹除。模型非pass/协议unknown、独立助手拒绝或预算/时钟异常按原规则停止，不重启或补样。

## 入口

```
backend/.venv/bin/python scripts/run_p15_agent_pilot.py --check
# 只有准确批准登记完成且新窗口有效后才允许以下动作：
backend/.venv/bin/python scripts/run_p15_agent_pilot.py --start
backend/.venv/bin/python scripts/run_p15_agent_pilot.py --step
backend/.venv/bin/python scripts/run_p15_agent_pilot.py --accept-report /private/tmp/edumind-p15-agent-pilot-p01/proposed-review-NN.json
# 纯只读：
backend/.venv/bin/python scripts/run_p15_agent_pilot.py --assessment
```

真实输出固定到新目录 `/private/tmp/edumind-p15-agent-pilot-p01`，已存在拒绝start，不复用旧账本。--step每次仅处理当前一个臂槽；暂停时不能隐式推进。pending批准在Key/.env、DNS、数据库/输出建立之前拒绝。预约持久化且唯一发送，未知保留占用；原始请求字节与实际HTTP body一致，原始响应和状态0600保存，Authorization不写入证据。

只读检查器先按共享批次Reducer重演全批检查点、不可逆停止及真实事件窗口，要求batch/calls投影一致，再重算原件摘要/事件链、准确输入/计划/审核/修复因果、版本/动作与独立报告。时间核验针对本机记录事实，不宣称独立可信时钟认证。证据通过与质量通过分别报告，固定分母含失败/未运行；degraded不计首次结构成功。T069采集任务完成不等于候选合格，T070须独立复核全量内容并复算首轮/最终成功、严重错误、误报/漏检、未知拒绝、修复/降级、时延和费用。小样本不能证明泛化、稳定P95或角色拆分因果，缺少消融必须区分引擎与多Agent贡献。

当前运行仍catalog_only，T038 blocked，旧批次/unknown/H封存保持；无生产/API/评分/掌握度接线，无push/merge/部署。
