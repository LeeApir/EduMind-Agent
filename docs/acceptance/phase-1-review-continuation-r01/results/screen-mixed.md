# screen-mixed：符合冻结预期，已实际人工确认

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
        "a5"
      ],
      "category": "code_safety",
      "condition_or_counterexample": "调用 total() 会执行 a[5]，但局部数组 a 只有 3 个元素，有效下标为 0 到 2；该越界读取是可达的未定义行为。",
      "impact": "该函数没有可保证的数值结果或正常返回，不能保证调用方获得所述返回值。",
      "severity": "severe"
    }
  ],
  "schema_version": "resource-review-v4",
  "scope": "unit",
  "unresolved": [
    "学生可见内容没有实现或追踪求和循环，也没有说明各步的状态变化或循环退出条件：解释仅称用 total 处理数组，代码直接返回越界元素，未展示循环；练习只问算术和、数组长度和是否有打印语句。因而缺少原请求要求的过程教学与过程掌握评估。"
  ],
  "verdict": "reject"
}
```

全部断言核对正确；a5准确引用/source 0–62 UTF8字节支持长度3与a[5]的具体严重缺陷。未实现求和循环、状态/退出教学缺失、过程测量缺失都已具体保留在unresolved；不从UB推导确定数值，也未将计划内部轨迹当作教学交付。

逐项断言与引用证据见 screen-mixed-claim-review.json。Codex核对通过不冒充实际Lee签核。

本条耗时9834ms，输入15457+输出757=16214tokens；内部有效推理档位/细分及费用未知。receipt `84b801ebc7fa66aff8e58f7049ff05562b513c1dd4d109d80f47419f17ab5898`。

新独立5槽逐条人工门禁，不改原停批/技术超时/独立重试记录。非正式全集或自动质量分数，T040/catalog_only保持。

后续用户已就本条实际结果确认“确认本条通过，继续”；准确receipt绑定签核见 `../assessments/screen-mixed.json`。本条符合预期不抵销后续安全样本的附带断言失败。
