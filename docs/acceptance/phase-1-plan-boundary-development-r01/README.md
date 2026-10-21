# 本批唯一有界开发验证 r01（T090）

**零真实调用准备包；材料及预算尚待本轮准确签核，不能直接run。** T089已提交`1b2b89d`，当前仅准备此一批，不恢复旧r02/单次重测余额，不新增第二候选或Prompt修订。H继续封存，T040 blocked，默认catalog_only。

生成配置仍DeepSeek `deepseek-flash/none`，但本包**生成请求0**；只测审核Luna `gpt-6-luna/high/8192`，单次60秒。固定`plan-check-prompt-v2`、`plan-semantic-input-v1`、完整业务模型输出`plan-review-result-v1`、record-v2服务端引用与既有Schema投影。只改变已批准的机械/语义输入分工，不同时换模型/推理档位/输出上限/学生生成流程。

## 完整材料与独立预标签

[逐项核对表](labels.md)＋[index.json](index.json)指向8份完整原文、输入快照、原计划和服务端绑定；全部`pending_Lee_for_this_batch`。D01/D08来自已暴露开发对照，内容不改；另有新编栈/链表/队列正确对照及预登记缺陷。都是开发材料，不是H、作者盲测或正式独立测试集，不能拿来证明泛化。由Lee核对全部输入和预标签后才授权调用；未来实际回答仍须独立核对，预标签签核不等于实际输出通过。

| ID | 类型 | 冻结目标 |
| --- | --- | --- |
| D01 | 原P01正确数组求和 | 干净pass/accept_plan |
| D02 | 新数组栈正确过程 | 干净pass/accept_plan |
| D03 | 新main内有效节点头插 | 干净pass/accept_plan |
| D04 | 新带size的循环队列 | 干净pass/accept_plan |
| D05 | 计划目标17与原文/轨迹19矛盾 | 具体检出，issue或needs_human，不能怪用户 |
| D06 | LIFO轨迹pop错称返回4 | 具体检出应11与计划4的矛盾，不能冒称UB |
| D07 | 长度3却无条件访问a[4] | reject；具体unsafe_plan/severe，不能推导UB数值 |
| D08 | 指定输入附件缺失 | needs_human；人工或合理要求补材料，不能断言确定非19 |

D08的新预标签明确允许server route=needs_human或clarify_user：本轮验证是否正确识别缺数据，而非强制一种补资料出口。原P03旧冻结标签/历史不改；这项新预标签须在调用前由Lee核对，不能依据未来回答调整。

业务代码无D01/P01、f83f/b333或17/19特判；数字只存在开发材料。错误摘要/引用版本/owner/op/plan版本等由代码在审核请求前拒绝，18种绑定负例、真实参考正文与节点身份负例及SQL最新版本门已由T089实际隔离PG验证；本包不为错误绑定浪费真实审核请求。当前Mock捕获只证明出站，无真实检出或评分结论。

## 精确预算与采集规则

[budget.json](budget.json)：**最多8次请求，每例1次；1小时硬截止**，含实际评分/人工核对等待。单次60秒，单例外层180秒且受剩余全局时间约束。输出配置求和65536（8×8192），不是输入＋输出总Token或费用上限；输入Token未知，实际完整请求字节可由captures核验。费用沿用用户不限政策，但新8次仍需准确授权。重试0、回退0、补样本0、候选1。

顺序严格D01→D08。为同时观察误拦和漏检，**语义失败保留后仍只采集其余预登记样本各一次**，不得修改材料、提示、参数或选择下一模型。任一已签核质量失败已经令8/8准入不可能，后续采集仅为定位误拦/漏检，不是调到通过。技术失败（HTTP/超时/Schema/用量/路由/冻结字节变化/不确定发送）立即停，不自动重试或用剩余额度另开轮次。此规则与旧r02首败停止不同，必须随本新包一并明确批准，旧轮继续停止。

新独立台账：`local-materials/phase-1-plan-boundary-development-r01/run.sqlite`。明确activate才启动1小时，不把准备/签核时间算为已启动，也不重置旧5小时。先预约再发、失败不退款，每例一次且8总量；CLI文件锁＋SQLite串行保护。中断后running/reserved不能重放。每次实际出站还须等于本例事先捕获的完整字节摘要。临时工件0600/目录0700，保留原始gzip及安全解码/完整Schema解析/用量/来源锚点、全部失败；无Key/认证头/DSN或原始包络入Git。

## 评分及准入／退出

新评测记录[evaluation.schema.json](evaluation.schema.json)／[空模板](evaluation-template.json)为`plan-boundary-evaluation-v1`，保留原全部断言/引用及五维分开评估，并新增dimensions.core_detection/false_block以免把附带错误等同于漏检或误拦。GPT可作草稿，只有Lee实际签核的记录才进入summary。collector中的`collected`只代表技术回答落盘，绝不是pass。

每条实际回答所有文本字段必须在claims证据清单中覆盖，一个字段的多个断言须逐项人工拆解。每个实际target/evidence anchor须逐项对应`调用号:锚点ID`和`/review_sources/调用号:锚点ID/source_text`，quote只能来自其实际字段。模型角色、语义摘录与完整服务端不可变pointer/digest/UTF8范围均可从result.json核对，不能借邻近字段。

`artifacts.request_sha256`是按顺序列出的calls.logical_request_sha256数组的canonical JSON摘要，response_sha256对应calls.parsed_sha256；每次实际线缆/原始与解码回答摘要另存，不冒称逻辑摘要就是原始字节摘要。模型自称pass、Mock pass、结构完整、GPT分数、人工放行均不自动提供质量真值或产品自动发布分子。

冻结通过要求：

1. 机械校验/出站/完整Schema/审计和全部8个实际结果完整；403项生产相关隔离PG及本包机制检查先通过。
2. 正确对照4/4干净pass，误拦0；两个计划矛盾均具体检出；可达越界拒绝且严重检出；缺数据正确保留不确定性，不能推“非19”。
3. 全部附带断言、严重度、建议和引用正确，独立签核8/8整体quality_success=true。核心拒绝正确而附带说法错误不能抵消；误拦、核心漏检、附带错误和引用错误分别记账。
4. 截止前8项独立评分齐备。未运行、未审、技术失败均不算通过，不通过就不动H。

任何一项不满足，本批开发准入失败。按用户已明确的退出决定：**已有签核课程作为正式产品；动态生成仅作为待审草稿能力，暂不承诺自动发布**。默认catalog_only、硬身份/安全/来源门及T040 blocked保持；不自动换模型、调Prompt、重测本例或追加新轮来避免退出。草稿能力的实际产品入口/人工工作量另按收敛范围细化，不能把现有诊断脚本宣传为已交付的公开草稿UI。

只有本批通过，才可以另行准备H实际验收；本包不授权读取H进入模型、生成、评估、调优、部署或开放动态自动发布。8例小开发筛选不能证明正式Schema≥98%、自动正式成功≥95%、严重召回≥90%或代表性错误率，人工通过不补正式自动分子。

## 执行入口及当前状态

```sh
backend/.venv/bin/python scripts/run_plan_boundary_batch.py check
```

freeze只写一次；本包批准后追加approval.json，绑定准确manifest、最多8次/3600秒、Lee全8标签核对及“技术失败停／语义失败采集固定余项”规则。随后activate→run --case D01→…→run --case D08。每次run仅一次调用；report显示采集/误拦/漏检/附带与引用问题的分账摘要。实际评测由`assess --case Dxx --evaluation /private/checked.json`保存，晚于截止不能补成准入通过；stop不可恢复。

原六停止SQLite与H封存摘要逐次校验，旧manifest不改。T089版本变化使旧runner不再适用于当前源码；旧源码归档用于历史复核，不将旧配置的成绩或余额转入本批。用户未提交的旧结果README编辑保留、不提交。

当前真实调用0、approval.json不存在、台账不存在；准确预算、全部8份材料与新预标签待Lee确认。离线证据及初失败见[validation.json](validation.json)、[offline-tests.json](offline-tests.json)，全部Mock不是实际模型成绩。
