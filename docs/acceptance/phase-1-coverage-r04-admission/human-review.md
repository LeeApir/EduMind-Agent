# r04 准入人工核对材料

四例是按用户标准预制的小诊断；请核对实际正文与预期，不能把助手标签当人工签核。
实际审核结果返回后仍须逐条核对，不自动继续。

执行根：`91c9d5f818d1f675f22691f9e318aec89fc6f0828bb070f245c86cc1b07ea1db`；最多4次，整窗保守上限8.768806元，输出总上限8192tokens。
无重试/回退；首次失败停止；原r03余额/halt不继承。

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

## trace-distributed → pass

材料摘要：`2c5828e7c104470f95e6f30424d417e01ff083ca64300674dfe5277f9924251a`

用户目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。

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

材料摘要：`d2829fc2fbaae99cb61d94bde3c63f38b6abc9f075313044863252701b5c8b5b`

用户目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。

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

材料摘要：`5ca788239ead6aea7bccd306fbae501346bc8a11a5d3d48bfd9ab13a2317706e`

用户目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。并用题目检验学生是否掌握循环过程。

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
