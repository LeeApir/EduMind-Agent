# r03 第1项：正确单元自动门禁通过，待人工核对

模型与本地路由均为pass，5个原始检查ID齐全，没有发现、未覆盖或未决项。
这是一份预制校准对照，并未生成或发布真实课程；不计正式T040成功分子。

请独立核对下列实际被审材料，确认是否接受这份正确对照的pass，再继续第2项目标遗漏反例。
完整计划、依赖、动作和锚点在 [冻结输入](../cases.json) 的correct-unit.material；
实际审核与摘要见 [correct-unit-01.json](correct-unit-01.json)。

## 本次目标与计划目标

用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。

- 逐步追踪total=2、7、16及i=3时不再访问数组的边界

## 实际讲解

a={2,5,9}，容量3，下标0、1、2。total初始为0。i=0读取a[0]=2后total=2；i=1读取a[1]=5后total=7；i=2读取a[2]=9后total=16。i增至3，i<3为假，停止循环，不访问a[3]，循环体恰执行3次。sum()返回16，不直接打印。

## 实际展示代码（未执行）

```c
#include <stddef.h>
int sum(void){int a[3]={2,5,9};int total=0;for(int i=0;i<3;i++)total+=a[i];return total;}
```

不打印；由调用方取得返回值。

- total从0开始依次变为2、7、16。
- i=3时i<3为假，停止且不访问a[3]。

## 实际练习与答案

1. [判断题] i=1这次循环结束后total=7。仅填 T 或 F（T=正确，F=错误）

   答案：T；解释：先加入a[0]=2，再加入a[1]=5，得到7。

2. [判断题] i=3时停止，循环体共执行3次。仅填 T 或 F（T=正确，F=错误）

   答案：T；解释：i只在0、1、2进入循环体；i=3不满足i<3。

3. [判断题] sum返回16表示它直接打印16。仅填 T 或 F（T=正确，F=错误）

   答案：F；解释：返回值交给调用方，本函数没有打印语句。

## 模型完整实际审核结果

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

本轮仅1次，12620输入+61输出=12681Token；预留2.184292元，高峰未命中用量参考0.025728元，
不是实际账单。其余3项未发、无人工continue记录，执行器停在HUMAN_CHECK_REQUIRED。
