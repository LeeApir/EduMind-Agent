# r02：整单元审核契约与目标范围校准

状态：零调用准备，**未批准真实请求与费用**。r01 的 2 次真实请求、原标签、失败结果、
批准与停止账本原样保留。T040 仍 blocked，T041/T042 不启动，catalog_only 不变。

## 修复内容与范围

沿 ADR-0015 的原规则实施：整单元不接受 revise，不启动全单元修正循环。
现在模型可见 Schema 固定 scope，unit 只允许 pass/reject/needs_human，Prompt v4.1
也明确约束；资源级保留原四结果及两次修正。本地检查不放松。统一持久结果 Schema
及批准 manifest 保留原字节，发送时只作规则投影。

审核核对服务端绑定目标和计划/场景目标，计划不能通过缩小目标回避用户要求。
图谱其他目标是参考；如果单元宣称全面覆盖节点，也必须兑现。缺 learner evidence
不构成“该学生有困难”的证据；真实不确定仍转人工。具体错误与安全缺陷不因范围缩小
而豁免。政策摘要绑定新 Prompt/范围版本，旧待审案按原失效规则处理。

详见 [review-scope-v4.1](../../agents/review-scope-v4.1.md)。这些是修复与工程测试，
不证明模型已可靠学会规则或能够达到正式门槛。

## 四个具体请求与建议标签

| 请求 | 样本与建议预期 | 上限（元） |
| --- | --- | ---: |
| correct-unit | 补全0→2→7→16、i=3停止的讲解和对应轨迹/边界题；仅承诺本单元目标，应自动pass | 2.183058 |
| missing-unit-objective | 同一计划、同一图谱仍承诺逐步轨迹/停止边界，讲解和练习却未直接教学/测量这些目标；须具体指出缺口，reject或needs_human | 2.181086 |
| reachable-safety | 调用时访问长度3数组的a[4]，须具体检出并归类code_safety | 2.154698 |
| fact-contradiction | 实际代码/轨迹16而讲解称返回18，须具体检出并归类fact | 2.183058 |

标签仍是**待用户独立复核的提案**。目标遗漏不强行归类 fact/difficulty；不能用类别匹配
代替具体证据。附带发现逐条核对，重大无据指控或漏检停止。不是移除图谱来保送正确对照：
所有样本继续提供完整原数组节点，正确/目标遗漏配对共享计划、目标与参考。

这是失败对照家族的校准，内容由助手预制；不声称统计独立，不并入正式100/20/20/10。
不重用第1次模型生成计划作后续模型生成证据。所有 C 均仅显示，不编译、不执行。

## 新预算与执行

固定 DeepSeek Responses / deepseek-flash；none、temperature=0、2048总输出Token/次，
包括推理；单次60秒，无工具/图片，无重试回退。四槽真实HTTP JSON字节、实际Schema、
参考/候选/动作与来源摘要均冻结在 cases.json/proposal.json。

**新轮总上限8.701900元，4请求，8192总输出Token。** 采用当日已核对的官方人民币
高峰未命中输入2元/百万、输出8元/百万与1M窗口保守解释1048576；
每槽微元 `2*(1048576+wire_bytes)+8*2048`。wire_bytes仅作正余量，不是Token估计。
这是保守预留，不是预计消费或账单；没有目标tokenizer证明，不能用少量实测直接降低上限。
证明见 token-cost-proof.json；正式运行前再次核对当日官方条款，变化或不明时停止。
[官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)、
[总输出定义](https://api-docs.deepseek.com/api/create-response/)。

```sh
backend/.venv/bin/python scripts/prepare_om_admission_r02.py --check
backend/.venv/bin/pytest -q scripts/tests/test_om_admission_r02.py
# 仅在准确新批准登记后可发送一槽；现在应退出2：
backend/.venv/bin/python scripts/run_om_admission_r02.py --run-one
```

执行器是旧逐次传输的独立模块实例，新base/private/run_id/批准根/账本；不会改写或
读取旧r01余额以取得发送权限。新的 run-approval.json 绑定本轮准确摘要/4次/8701900微元/
标签摘要/用户真实答复/当日条款日期。没有自动批准开关，当前目录无该批准文件。
到北京时间2026-10-18 23:59:59失效；每次先持久预留，再读版本绑定的0600密钥文件并出站。
失败/取消/未知用量不退槽；一个请求完成后等待准确收据的真实人工continue，最多4次。
本地契约故障在新r02映射 INVALID_OUTPUT；r01既有 SAFETY_FAILURE/halt 不修改。

小诊断通过也不能启动全量验收。八类诊断、独立正式范围/真值、实际派生槽执行器与正式
预算仍须冻结批准。自动质量分母和阈值保留，人工兜底不补自动分子。不沿用r01余量或旧r11。
