# r05 / v4.4 首条完整正例：自动门禁通过，待人工核对

已按准确批准真实发送1次。模型及本地均pass，五个原始检查ID齐全，没有发现、未覆盖或未决项。
r04中把参考图谱其他目标当必教项、把未承诺动画当未决项的误拒，在本次完整正例未再出现。
这只是一个预制正例；其余三例未测试，不等于v4.4完整有效或正式T040通过。

原始目标（来自绑定原快照，不从计划反推）：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。

用量：14247输入 + 61输出 = 14308tokens。
预留2.198400元；高峰未命中用量参考0.028982元，非实际账单。

## trace-complete → pass

材料摘要：`e422c5a587b691edb34e26de69d40562e601276b0b91ebd069db8e231c3a0701`

计划goal（保持原文）：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。

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
  "unresolved": [],
  "verdict": "pass"
}
```

## 核对边界

代码及全部学生内容与r04相同。独立固定算术检查得到2/7/16、i=3时i<3为假且返回16；未执行任意C代码。
请核对上述实际材料是否为合格完整正例、是否接受本次pass。确认只授权在现有r05预算内发第二条分散覆盖，不解锁后续事实/安全或正式验收。
尚未生成对真实结果的人工继续记录；余3未发，r04旧halt保留。
