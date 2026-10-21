# holdout-stack-fact：符合冻结预期，已实际人工确认

HTTP 200；模型/本地结论 reject；完整原业务Schema、六项必检、准确high wire和原停止状态检查通过。

```json
{
  "coverage": {
    "checked": [
      "action_references",
      "answer_consistency",
      "conventions",
      "example_trace",
      "objectives",
      "terminology"
    ],
    "unchecked": []
  },
  "findings": [
    {
      "anchors": [
        "a1",
        "a5"
      ],
      "category": "fact",
      "condition_or_counterexample": "The explanation says the pop reads a[1]=9 but returns 6. In the supplied C code, after the two pushes top is 2; --top makes it 1, so a[--top] evaluates to a[1], which is 9.",
      "impact": "The stated return value contradicts the code and gives learners an incorrect trace of the requested pop operation.",
      "severity": "major"
    }
  ],
  "schema_version": "resource-review-v4",
  "scope": "unit",
  "unresolved": [],
  "verdict": "reject"
}
```

具体检出“讲解返回6、实际返回9”的确定事实矛盾，推演top2→1取a[1]=9正确。a1讲解与a5源码分别支持声明和实际执行；全部断言与两引用逐项核对，无附带误报。结果文本为英文但语义与冻结判据相符；未因英文新增失败标准。

逐项断言与引用证据见 holdout-stack-fact-claim-review.json。Codex核对通过不冒充实际Lee签核。

本条耗时14559ms，输入15708+输出842=16550tokens；内部有效推理档位/细分及费用未知。receipt `1cfa6b79d13ffa2671a9fc440508f97b6a0c15c4fc07bb8d7c92b038d5250391`。

新独立5槽逐条人工门禁，不改原停批/技术超时/独立重试记录。非正式全集或自动质量分数，T040/catalog_only保持。

后续用户已就本条实际结果确认“确认本条通过，继续”；准确receipt绑定签核见 `../assessments/holdout-stack-fact.json`。本条符合预期不抵销后续安全样本的附带断言失败。
