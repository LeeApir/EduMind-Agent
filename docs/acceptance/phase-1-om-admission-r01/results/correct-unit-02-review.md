# 第2次真实请求：正确整单元审核未通过，当前轮次停止

接口已成功返回结构化结果，真实模型/实际 wire 绑定与 Schema 校验通过。
失败是本地整单元协议检查：模型返回 `scope=unit, verdict=revise`；本地禁止此组合。
对原结果离线重放得到 `REVIEW_PROTOCOL_INVALID`，没有新增网络请求。

## 查明的问题（助手分析，非人工签核）

1. **模型可见契约与本地规则不一致**：共享审核 Schema 仍允许 `revise`，运行时 Prompt
   未明确整单元禁止 `revise`，但本地路由器会拒绝。应先在零调用修复中统一，不能靠重试碰结果。
2. **“正确对照”的范围有歧义**：该样本只讲求和与下标边界，引用的数组节点另列访问复杂度、
   插入删除目标。模型指出缺少这些目标，不能直接说全部是无据误报；预期自动 pass 的标签需要复核。
3. **分类与证据仍有问题**：模型把目标覆盖不足标为 `fact`；在明确没有学习者证据时仍给
   `difficulty`。它还假设此单元必须纠正节点的所有常见误解。这些判断须按具体目标独立核对。

独立账本的错误标签为 `SAFETY_FAILURE`，来自通用异常分类器对本地契约异常的兜底映射，
**不表示发现 Key 泄露或样本存在内存安全漏洞**。原账本和结果原样保留，不手改错误为成功。

## 用量与停止状态

- 第2次：11491输入 + 650输出 = 12141 Token；预留2.177396元；高峰未命中用量参考0.028182元。
- 累计2次：14566 Token；预留4.301416元；高峰用量参考0.037940元，均非实际账单。
- 账本持久停止；安全缺陷/事实矛盾两槽未发送；不重试、不扩额、不领取T041，不开放动态模式。
- T040依旧 blocked，不改旧标签或分母，不将人工继续首槽算作正式自动质量分子。

完整实际返回及准确摘要见 [correct-unit-02.json](correct-unit-02.json)。
后续应先零调用修正协议、明确“节点全部目标”与“本次单元目标”的边界并重新核对对照标签；
如需再做真实调用，必须另冻组合和预算，不能沿用本轮余量自动重开。

## 模型实际完整审核结果

```json
{
  "coverage": {
    "checked": [
      "action_references",
      "answer_consistency",
      "conventions",
      "example_trace",
      "terminology",
      "explanation_content",
      "code_content",
      "exercise_content",
      "plan_objective_alignment",
      "node_learning_objectives",
      "node_common_misconceptions",
      "anchor_catalog_consistency"
    ],
    "unchecked": [
      "Independent verification of the proposed trace against the graph source (reference_context explicitly marks the trace as not independently verified)",
      "Learner evidence (learner_evidence is empty, so no empirical difficulty or misconception data is available)"
    ]
  },
  "findings": [
    {
      "anchors": [
        "a1"
      ],
      "category": "fact",
      "condition_or_counterexample": "Explanation resource states 数组a={2,5,9}，合法下标0至2。sum()返回16；函数不打印。 The plan's stated goal and objective are to trace the C summation loop and explain index bounds 0–2 and return value 16, but the node's explicit learning objectives are 说出下标访问的时间复杂度 and 说明连续存储对插入和删除的影响. The explanation contains no statement about index-access time complexity and no statement about the effect of contiguous storage on insertion/deletion.",
      "impact": "The explanation scene does not cover the node's declared learning objectives; a learner completing this unit receives no instruction on the required complexity or insertion/deletion consequences, so the unit cannot satisfy its mastery target.",
      "severity": "major"
    },
    {
      "anchors": [
        "a1",
        "a9",
        "a13",
        "a17"
      ],
      "category": "misconception",
      "condition_or_counterexample": "The node lists common_misconceptions including 数组插入总是 O(1) and 数组每次访问都要从头遍历. The explanation and all three exercise items only address index bounds, arithmetic 2+5+9=16, and whether a return value is printed. No item or explanation confronts either listed misconception.",
      "impact": "Learners holding the documented misconceptions receive no corrective feedback; the exercises can be answered correctly while the misconceptions remain intact, undermining the unit's misconception-remediation purpose.",
      "severity": "major"
    },
    {
      "anchors": [
        "a9",
        "a13",
        "a17"
      ],
      "category": "difficulty",
      "condition_or_counterexample": "All three exercise items are true/false with single-character answers (T/F) and the node difficulty is 1. The plan objective is 追踪数组求和的边界和结果, but no item requires tracing the loop, producing the intermediate totals 2,7,16, or reasoning about the boundary condition i<3.",
      "impact": "The assessment does not exercise the stated tracing objective; a learner can pass by recalling the arithmetic fact 2+5+9=16 and the general rule that return values are not printed, without demonstrating the intended trace skill.",
      "severity": "minor"
    }
  ],
  "schema_version": "resource-review-v4",
  "scope": "unit",
  "unresolved": [
    "The reference_context scope states 'Partial graph; proposed trace is not independently verified evidence', so alignment of the unit with the full graph beyond the array node cannot be confirmed.",
    "No learner evidence is supplied; difficulty and misconception findings rest on resource content versus declared node metadata only."
  ],
  "verdict": "revise"
}
```
