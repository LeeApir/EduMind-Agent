# r04 第1项：正确对照未通过，已停止

真实发送1次，协议、Schema、精确wire及模型绑定通过。模型返回needs_human，五检查ID齐全，无findings。
本地离线重放为COVERAGE_ROUTE_MISMATCH，账本INVALID_OUTPUT持久停止；余3条未发。

模型承认完整total=2/7/16、i=3退出，却要求补齐参考节点的O(1)访问、插入删除及其他误区，
并以未提供已验证动画为未决项。冻结目标只承诺固定求和过程；graph_role明确不要求整个节点。
助手判读为审核范围扩大/正确对照转人工，不是API不可调用，也不是严重错误漏检。
尚未代填对实际结果的人工确认，v4.3有效性不能据此宣称通过。

用量：13539输入 + 305输出 = 13844tokens。
预留2.192766元；高峰未命中用量参考0.029518元，非实际账单。

## trace-complete → pass

材料摘要：`9dd312b035c8626c054aeac343e0d80127e97e51cc3c08de78e55cd29d0e27e2`

用户目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。

计划目标：逐步追踪total=2、7、16及i=3时不再访问数组的边界

### explanation

a={2,5,9}，容量3，下标0、1、2。total初始为0。i=0读取a[0]=2后total=2；i=1读取a[1]=5后total=7；i=2读取a[2]=9后total=16。i增至3，i<3为假，停止循环，不访问a[3]，循环体恰执行3次。sum()返回16，不直接打印。

### code

```c
#include <stddef.h>
int sum(void){int a[3]={2,5,9};int total=0;for(int i=0;i<3;i++)total+=a[i];return total;}
```

不打印；由调用方取得返回值。

- total从0开始依次变为2、7、16。
- i=3时i<3为假，停止且不访问a[3]。

### exercise

- q1：[判断题] i=1这次循环结束后total=7。仅填 T 或 F（T=正确，F=错误）
  答案：T；提交后解析：先加入a[0]=2，再加入a[1]=5，得到7。

- q2：[判断题] i=3时停止，循环体共执行3次。仅填 T 或 F（T=正确，F=错误）
  答案：T；提交后解析：i只在0、1、2进入循环体；i=3不满足i<3。

- q3：[判断题] sum返回16表示它直接打印16。仅填 T 或 F（T=正确，F=错误）
  答案：F；提交后解析：返回值交给调用方，本函数没有打印语句。

内部计划（不计交付）：
```json
{
  "input_description": "a={2,5,9}",
  "initial_state": "total=0",
  "steps": [
    {
      "operation": "i=0,1,2累加a[i]",
      "expected_state": "total依次2,7,16",
      "expected_output": null
    },
    {
      "operation": "i=3检查i<3",
      "expected_state": "条件为假，退出且不访问a[3]",
      "expected_output": "16"
    }
  ]
}
```


## 模型完整实际意见

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
  "unresolved": [
    "Student-visible goal coverage is incomplete for the server-bound goal and the node's learning objectives. The delivered unit only traces the sum loop over a={2,5,9} (total=2,7,16, exit at i=3, return 16). It does not teach the node objectives '说出下标访问的时间复杂度' (state the time complexity of index access) or '说明连续存储对插入和删除的影响' (explain the effect of contiguous storage on insertion/deletion), and it does not address the node's common misconceptions ('数组每次访问都要从头遍历', '数组插入总是 O(1)'). The plan itself is narrower than the server-bound goal, so the plan cannot excuse the missing parts. Exact missing support: student-visible explanation/code/exercise content covering O(1) index access and the cost of insertion/deletion in a contiguous array.",
    "No verified student-visible animation evidence was supplied in this three-resource request; the plan's ai_context mentions a contiguous-cell/index-sprite illustration, but that is internal plan/reference context, not delivered teaching evidence, so any animation-based coverage claim cannot be assessed."
  ],
  "verdict": "needs_human"
}
```

## 冻结范围指令

```json
{
  "allowed_verdicts": [
    "pass",
    "reject",
    "needs_human"
  ],
  "coverage_standard": "student-visible-goal-coverage-v1",
  "coverage_target": "server-bound goal and selected plan/scene objectives",
  "graph_role": "partial reference, not automatic full-node certification",
  "missing_learner_evidence_is_known_difficulty": false,
  "plan_is_evidence": false,
  "scope": "unit",
  "unit_responsibilities": [
    "cross-resource consistency",
    "student-visible goal coverage",
    "questions use the assigned process knowledge"
  ],
  "version": "goal-bound-review-scope-v1"
}
```

原系统指令明确：

> A graph node's other objectives and misconception examples are reference context, not a requirement to cover the entire node in every single learning unit.

本轮按首败停止；不重试、改分、改Prompt或发余3槽。需要先独立核对上述实际材料/意见，再决定下一步；正式T040仍blocked。
