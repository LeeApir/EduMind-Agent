# v4.4 / r05 四对照与准确预算

执行根：`fdbb5c6563289f5f61ded5cf473fd8d3ba5dba204fd3045e2fc18eb9d8e145e2`。

最多4次，整窗保守上限8.791654元；总输出8192tokens。
无重试/回退，首败停止。每条真实结果需独立核对后才继续，不能只看路由相同。
四组学生envelope、内容digest及完整计划与r04完全相同；只换输入契约和必要版本/身份绑定。
原始目标从旧冻结input_snapshot.goal原文包装到metadata.goal，不从计划推测。

- trace-complete 原始请求：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
  原快照摘要：`0fb8ac9c9c1776b1d85f2a8381f916f134ce0e5775b465217277aae67faed97e`；新绑定：`ef8f69cb35a786584eff9a40380be6cdae7e454f792b3424d78c99627083c4d9`。
- trace-distributed 原始请求：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
  原快照摘要：`0fb8ac9c9c1776b1d85f2a8381f916f134ce0e5775b465217277aae67faed97e`；新绑定：`ef8f69cb35a786584eff9a40380be6cdae7e454f792b3424d78c99627083c4d9`。
- plan-only-gap 原始请求：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
  原快照摘要：`0fb8ac9c9c1776b1d85f2a8381f916f134ce0e5775b465217277aae67faed97e`；新绑定：`ef8f69cb35a786584eff9a40380be6cdae7e454f792b3424d78c99627083c4d9`。
- assessment-gap 原始请求：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。并用题目检验学生是否掌握循环过程。
  原快照摘要：`e2447f1cdeb5ff80e0107d08dacc1c5ac21f8b1f5c516dcc198909f1a66150a5`；新绑定：`8ef875aae05da2456766aa408bc2480eb889d2e97f39a119bd21936d356cbba5`。

判据保持pass/pass/needs_human/needs_human，后两例必须具体说明真实缺口及位置，不虚构事实错误。
本包只含四覆盖对照；四例通过且人工核对后，另做事实/安全等诊断，再进入正式验收。

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

## assessment-gap → needs_human

材料摘要：`530af5709da6a592e94bd3f5128892b76a66337a74a84d0a914f1cd1075d92e3`

计划goal（保持原文）：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。并用题目检验学生是否掌握循环过程。

计划目标：逐步追踪total=2、7、16及i=3时不再访问数组的边界，用题目检验中间状态和退出条件知识。

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
