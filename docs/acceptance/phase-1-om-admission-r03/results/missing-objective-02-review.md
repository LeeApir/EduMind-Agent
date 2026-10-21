# r03 第2项：目标遗漏反例未满足预期，当前轮次停止

实际接口/Schema/范围/5个检查ID均通过。模型仍返回pass，无发现、未知或未覆盖项。
冻结预期是具体指出覆盖缺口并reject或needs_human，因此本次诊断门禁失败并持久halt。
不是网络、认证、截断或检查ID问题。余下安全/事实两项未发送，不自动重试。

## 必须先人工裁定的样本问题

该反例删除了讲解中的逐步累加/退出过程及对应练习，而计划仍承诺逐步轨迹目标。
但代码依然是完整正确循环，审核器看到的共享计划也保留了预期轨迹。因此，是否已经足够
构成“教学目标未覆盖”，需要独立核对；不能仅因标签写负例就宣称严重错误漏检。
不改原标签、结果或失败门禁，也不把本次作为正式质量样本。先明确覆盖标准，再决定策略。

## 模型实际看到的目标与计划轨迹

用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。

- 逐步追踪total=2、7、16及i=3时不再访问数组的边界

```json
{
  "input_description": "a={2,5,9}",
  "initial_state": "total=0",
  "steps": [
    {
      "operation": "遍历i=0,1,2并累加a[i]",
      "expected_state": "total依次为2,7,16",
      "expected_output": "16"
    }
  ]
}
```

## 实际讲解

a={2,5,9}，容量3，下标0、1、2。sum()返回16，不直接打印。

## 实际代码（未执行）

```c
#include <stddef.h>
int sum(void){int a[3]={2,5,9};int total=0;for(int i=0;i<3;i++)total+=a[i];return total;}
```

不打印；由调用方取得返回值。

- 遍历并求和后返回结果。

## 实际练习

1. [判断题] 长度为3的数组合法下标为0、1、2。仅填 T 或 F（T=正确，F=错误）

   答案：T；解释：从0开始，最后下标为长度减1。

2. [判断题] 2+5+9=16。仅填 T 或 F（T=正确，F=错误）

   答案：T；解释：2+5=7，7+9=16。

3. [判断题] 返回值必然直接打印到屏幕。仅填 T 或 F（T=正确，F=错误）

   答案：F；解释：返回值传给调用方；本例没有打印语句。

## 模型完整结果

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

完整冻结计划/参考/动作/锚点见[原输入](../cases.json)中missing-unit-objective.material；
[结果证据](missing-objective-02.json)包含准确摘要、原失败收据与用量。
本次12197Token，高峰用量参考0.024760元；r03累计2次/24878Token，预留4.366600元，
高峰用量参考0.050488元（不是实际账单）。T040仍blocked，正式质量与T041未解锁。
