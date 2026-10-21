# 配置对照r01：首条low完整正例实际结果

预算和7组材料/判据已获本次用户批准。本次仅发送候选完整正例一次；实际结果尚未人工确认。

模型及本地路由均pass；五检查ID齐全，无findings/unchecked/unresolved。本次low+JSONSchema、wire及模型绑定通过，未截断。这不是七组通过或分类误报已修复的证明，当前none基线尚未发送。

准确收据：`50810c2ca1f28604dbeeed2b7e84d92894f80f8297f6f9ac53c9e123927b82e6`。
本次14272输入+1515总输出（含思考）=15787 tokens；没有单独保存思考/可见输出拆分，不能自行推算。
预留2.198398元；高峰未缓存用量参考0.040664元，非实际账单。

## 实际目标与学生内容

用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。

### explanation

```json
{
  "markdown": "a={2,5,9}，容量3，下标0、1、2。total初始为0。i=0读取a[0]=2后total=2；i=1读取a[1]=5后total=7；i=2读取a[2]=9后total=16。i增至3，i<3为假，停止循环，不访问a[3]，循环体恰执行3次。sum()返回16，不直接打印。"
}
```

### code

```json
{
  "language": "C",
  "source": "#include <stddef.h>\nint sum(void){int a[3]={2,5,9};int total=0;for(int i=0;i<3;i++)total+=a[i];return total;}",
  "expected_output": "不打印；由调用方取得返回值。",
  "key_steps": [
    "total从0开始依次变为2、7、16。",
    "i=3时i<3为假，停止且不访问a[3]。"
  ],
  "display_only": true
}
```

### exercise

```json
{
  "items": [
    {
      "id": "q1",
      "question": "[判断题] i=1这次循环结束后total=7。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "先加入a[0]=2，再加入a[1]=5，得到7。"
    },
    {
      "id": "q2",
      "question": "[判断题] i=3时停止，循环体共执行3次。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "i只在0、1、2进入循环体；i=3不满足i<3。"
    },
    {
      "id": "q3",
      "question": "[判断题] sum返回16表示它直接打印16。仅填 T 或 F（T=正确，F=错误）",
      "answer": "F",
      "explanation": "返回值交给调用方，本函数没有打印语句。"
    }
  ]
}
```

## 实际审核完整回答

```json
{
  "coverage": {
    "checked": [
      "action_references",
      "answer_consistency",
      "conventions",
      "example_trace",
      "terminology"
    ],
    "unchecked": []
  },
  "findings": [],
  "schema_version": "resource-review-v4",
  "scope": "unit",
  "unresolved": [],
  "verdict": "pass"
}
```

## 本地判定与下一步

```json
{
  "arm": "candidate",
  "criterion_signal": true,
  "human_concrete_detection_check_required": true,
  "note": "Category/route matching alone is not semantic success. Inspect actual anchors, omissions, contradictions and severity before continuation.",
  "route": {
    "policy_version": "hybrid-review-v1",
    "reason_codes": [],
    "verdict": "pass"
  },
  "semantic_detection_confirmed": false
}
```

执行助手核对：讲解及代码步骤明确total=2/7/16和i=3退出；练习要求中间状态和退出知识，返回/打印区分一致。本例完整覆盖，当前pass与材料吻合；这不代替用户独立确认。

当前1条complete/no halt，停HUMAN_CHECK_REQUIRED。余13条未发，未生成首条真实human continue。下条为trace-complete:baseline，已有预算无需重批，但需先确认本次准确实际结果。r05原halt和生产默认不变。
