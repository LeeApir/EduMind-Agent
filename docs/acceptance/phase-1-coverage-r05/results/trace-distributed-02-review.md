# r05 / v4.4 第二条分散覆盖正例：自动门禁通过，待人工核对

用户确认首条完整正例实际pass后，在原批准预算内仅发送本条一次。
模型及本地均pass，五检查ID齐全，没有发现、未覆盖或未决项。讲解没有重复状态轨迹，
代码key_steps仍明确2/7/16和i=3退出，练习与解析提供中间状态/退出知识。
本次没有因支持分布在不同载体而误拒；未出现额外图谱目标或未承诺动画要求。

原始目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。

本次14193输入+61输出=14254tokens；本轮累计2次/28562tokens。
本次预留2.198032元，累计预留4.396432元；高峰未命中用量参考本次0.028874元、累计0.057856元，均非实际账单。

## trace-distributed → pass

材料摘要：`87bcc0bc29edb86451809aedc204f15d4defa5813190a5aeb6961d08075f2d04`

计划goal（保持原文）：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。

计划目标：逐步追踪total=2、7、16及i=3时不再访问数组的边界

### explanation

固定输入a={2,5,9}；sum无外部参数，返回16，不直接打印。

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
  "unresolved": [],
  "verdict": "pass"
}
```

## 核对边界

请核对分散在代码关键步骤和练习解析的支持是否满足本单元过程目标、是否接受本次pass。
两个正例自动通过，尚不证明遗漏检出能力；过程支持缺失、过程测量缺失两反例均未发。
本条实际结果尚未代填人工continue；确认后才在原预算内发第三条plan-only-gap一次，无需重批费用。
事实/安全等诊断和正式T040仍在四例通过后的门禁之后，r04原halt不改。
