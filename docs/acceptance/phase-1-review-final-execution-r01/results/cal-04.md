# B/cal-04：已教未考，needs_human符合冻结预期

用户确认cal-03实际结果后，cal-04真实1次返回needs_human，本地SEMANTIC_UNRESOLVED。HTTP200、gpt-6-luna正常完成，准确high请求/原完整Schema/六ID/raw21349字节完整与usage通过；findings/unchecked空，未决一条：

> The exercise questions ask only for arithmetic sums or whether a sum is true; answering them does not require tracing the loop's accumulator/index states or identifying its exit condition. The explanation and code key steps teach those details, but the requested check of mastery of that process is not delivered by the questions. Add student-visible exercise questions that require process knowledge.

## 全部断言与证据核对

- 三道题确实只问3+8+4、8+4+3的整数结果，以及3+8+4=16的真假；正确答案15/15/F。无需分析循环下标、累计状态或首次失败条件即可答出。即使解析出现11/12等算术中间和，也没有使题干要求追踪实际循环。
- 讲解已经明确s=0→3→11→15和i=3时条件为假退出，代码步骤包括处理下标0/1/2和i3退出。模型认可这些过程教学，没有误称未教。
- 原始目标明确要求用题目检查过程，故指出测量缺口有目标依据；不是把图谱其他目标当必达项，不依赖未知学情推定难度。
- “补充需要过程知识的题”只描述当前承诺缺口，不禁止判断/填空题型，不要求额外媒体，不发明做题前时序，也没把题干错误命题当课程事实或代码错误。

全部断言核对见cal-04-claim-review.json。本例没有finding引用，不能因此声称引用定位能力已通过。当前needs_human是诊断符合预期，不是课程发布pass；实际Lee结果确认仍pending，材料真值或前三例确认不能预签这一条。

本条输入15995、输出548，共16543tokens，调用部分7884ms。累计5次输入79980、输出2182，共82162tokens，调用部分40026ms；不是端到端P95，compat与cal-01同材重复不计两个独立样本。实际推理细分/内部有效档位与账单未知，原始响应/思考正文不保存；receipt摘要`f5c72624152fefa69009917b4f43b702c06ab7c43ac9bb8c700cc2032e54eb44`。

## 四例阶段当前状态

| 校准材料 | 冻结预期 | 实际模型结果 | 实际人工核对 |
| --- | --- | --- | --- |
| cal-01完整覆盖 | pass | pass | 已确认 |
| cal-02原样分散覆盖 | pass | pass | 已确认 |
| cal-03缺过程教学 | needs_human | needs_human，具体教学缺口 | 已确认 |
| cal-04已教但只测算术 | needs_human | needs_human，具体测量缺口 | 待确认 |

四例是受历史失败启发制作的判据校准，不是正式独立测试集；目前只能说模型输出符合预期，最后真实人工确认完成前不宣布本阶段签核完成。

WAITING_HUMAN_REVIEW，无halt。cal-04实际完整性/全部断言/全部引用/判据确认后，才进入既有授权C阶段第一条screen-fact（明确17与实际15矛盾），此时不再追加候选或预算。后7条（3严重、4旧未参与近期修复材料）均未发，严重召回尚未检验。原含人工截止**2026-10-21T09:44:16.144212+08:00**不重计；任何失败停止本批研发转交付范围讨论。

T040 blocked、catalog_only和旧low退役失败/未发保持。源码未改，原106证据沿用9288782，本次复核484源、原完整Schema/wire/收据及旧停止。
