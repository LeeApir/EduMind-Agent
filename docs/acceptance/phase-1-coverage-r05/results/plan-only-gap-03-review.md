# r05 / v4.4 第3条过程支持缺失：指出缺口，但分类未通过

用户确认第2条实际pass后，本次仅真实发送plan-only-gap一次。
模型返回needs_human，五检查ID齐全。它具体指出缺total=2/7/16、i=3退出教学及过程题支持，
这一主要缺口与实际内容吻合；不能把本次描述为“完全没检出教学缺口”。

但是findings另列了minor/fact：没有sum调用示例。模型同时明确称它是presentation gap而非
错误算术，并承认算术与return正确。未承诺完整可执行调用示例时，这不能直接构成事实矛盾；
当前冻结判据要求纯覆盖不足不虚构fact finding，因此本地PURE_COVERAGE_FINDING_INVALID失败。
协议、Schema、实际wire与模型绑定均通过，账本INVALID_OUTPUT是本地准入失败，不是API不可调用。
本轮已持久停止，第四条assessment-gap未发送，不重试或修改冻结标签/Prompt。

原始目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。

本次13588输入+455输出=14043tokens；累计3次/42605tokens。
本次预留2.196416元、累计6.592848元；高峰未命中用量参考本次0.030816元、累计0.088672元，非实际账单。

## plan-only-gap → needs_human

材料摘要：`c19deec758d9756b548b797f9af13dcff587143d523c1a25be76d9dd96e74ab3`

计划goal（保持原文）：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。

计划目标：逐步追踪total=2、7、16及i=3时不再访问数组的边界

### explanation

a={2,5,9}，容量3，下标0、1、2。sum()返回16，不直接打印。

### code

```c
#include <stddef.h>
int sum(void){int a[3]={2,5,9};int total=0;for(int i=0;i<3;i++)total+=a[i];return total;}
```

不打印；由调用方取得返回值。

- 遍历并求和后返回结果。

### exercise

- q1：[判断题] 长度为3的数组合法下标为0、1、2。仅填 T 或 F（T=正确，F=错误）
  答案：T；提交后解析：从0开始，最后下标为长度减1。

- q2：[判断题] 2+5+9=16。仅填 T 或 F（T=正确，F=错误）
  答案：T；提交后解析：2+5=7，7+9=16。

- q3：[判断题] 返回值必然直接打印到屏幕。仅填 T 或 F（T=正确，F=错误）
  答案：F；提交后解析：返回值传给调用方；本例没有打印语句。

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
  "findings": [
    {
      "anchors": [
        "a1"
      ],
      "category": "fact",
      "condition_or_counterexample": "Explanation resource states \"sum()返回16，不直接打印。\" The code resource defines `int sum(void)` with no parameters and no caller; the explanation's phrasing implies a callable function whose return value is observed, but no call site exists in the supplied material. This is a presentation gap rather than a false arithmetic claim.",
      "impact": "Learners see a return value asserted without any visible invocation, which may weaken the connection between the function body and the claimed return of 16; however the arithmetic and return statement are correct, so this is minor.",
      "severity": "minor"
    }
  ],
  "schema_version": "resource-review-v4",
  "scope": "unit",
  "unresolved": [
    "Student-visible goal coverage for the TRACE/EXPLAIN-PROCESS objective: the authoritative request asks to trace the summation loop and explain indices 0–2 and the return value 16. The explanation resource only states the array, capacity, indices, and that sum() returns 16 without printing; it does not show the step-by-step total=2,7,16 progression or the i=3 termination condition. The code resource contains the loop but no student-visible trace of key state changes or exit condition. The exercise items ask only whether indices 0,1,2 are valid, whether 2+5+9=16, and whether a return value is necessarily printed; none require tracing total across iterations or explaining the i=3 boundary. The plan's shared_example and key_steps contain the trace, but these are internal plan/reference fields, not delivered teaching evidence. Therefore the unit does not visibly deliver the requested process trace or boundary explanation.",
    "No verified animation evidence is supplied; no explicit animation promise is present, so absent animation is not treated as a defect.",
    "The code resource is marked display_only and has no call site; whether learners are expected to infer the caller context is not specified in the supplied material."
  ],
  "verdict": "needs_human"
}
```

## 分开记录的结论

- 具体教学缺口：已指出，需人工独立核对实际意见。
- 预期路由：needs_human，匹配。
- 纯缺口分类要求：额外fact finding，不匹配，原判据不改分。
- 附带问题：未承诺动画的说明仍列在unresolved；plan/key_steps取材位置表述不够准确。实际code.key_steps只有“遍历并求和后返回结果”。
- 后续：r05停止，第四条未测；事实/安全等其他诊断及正式T040不启动。
