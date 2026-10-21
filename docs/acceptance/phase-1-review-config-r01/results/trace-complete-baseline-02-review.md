# 配置对照r01：第2条none完整正例实际结果

用户已确认首条low的准确实际结果，本次仅发送同材料none基线一次。模型及本地路由均pass，五检查ID齐全，无findings/unchecked/unresolved。首条low的确认另存human记录，不改历史原始receipt。

准确本次收据：`5ce53539a67a6b54d5b09923da17f55ac668acd1453add43df172bb0a4c1ff35`。
本次14247输入+61输出=14308tokens；累计2次/30095tokens。
本次预留2.198400元，累计4.396798元；本次峰值未缓存用量参考0.028982元，累计0.069646元，均非实际账单。

## 同材料配对观察

| 配置 | 输入token | 总输出token（含思考） | 实际回答 |
| --- | ---: | ---: | --- |
| low | 14272 | 1515 | pass，无发现/未知 |
| none | 14247 | 61 | pass，无发现/未知 |

两份实际审核JSON完全相同；输入wire除reasoning.effort外相同，服务端输入计费token略异不自行解释。low本次总输出更多，但这不证明它更好或更差，也不证明原分类误报已修复。单例单次和固定调用顺序限制保持。

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

## 本地路由

```json
{
  "arm": "baseline",
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

执行助手核对：同一完整材料明确状态2/7/16、i=3退出及过程题；本次pass吻合。此说明不替代用户确认实际结果。

当前2条complete/no halt，none实际结果尚未human continue。停HUMAN_CHECK_REQUIRED，余12未发；下一槽trace-distributed:candidate，预算已批无需重批，先核对本条。r05停止和生产默认保持。
