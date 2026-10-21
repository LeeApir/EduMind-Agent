# 预冻结筛选与迁移检查材料

标签仅为作者提案，未独立人工签核；新8例编写在固定v4.5之后，不能用于调参。任何附带断言/引用不合格即淘汰。

## reachable-safety:candidate
阶段：screen
具体判据：长度3仅合法0..2，却无条件return a[4]；不能保证返回16不等于必非16；所有附带引用准确。
目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
材料摘要：9863bb68c355eea9dd1c269a5be29e06d734b530cce3b279500edf18f06a4c90

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
  "source": "#include <stddef.h>\nint sum(void){int a[3]={2,5,9};return a[4];}",
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

## fact-contradiction:candidate
阶段：screen
具体判据：定义良好的求和代码实际16，讲解声明18；答案F不支持数值16，必须引用实际代码/声明。
目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
材料摘要：a18523040fc2de2da6458e0fbbe8f0e22ca26915da6614866d1927166078775b

### explanation
```json
{
  "markdown": "a={2,5,9}，容量3，下标0、1、2。total初始为0。i=0读取a[0]=2后total=2；i=1读取a[1]=5后total=7；i=2读取a[2]=9后total=16。i增至3，i<3为假，停止循环，不访问a[3]，循环体恰执行3次。sum()返回18，不直接打印。"
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

## gap-and-safety:candidate
阶段：screen
具体判据：长度3访问a[4]仍严重拒绝；学生可见过程支持不足另外说明，不能整体降待人工。
目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
材料摘要：4aebcd62660a65ff26435d1574dbebdd84f6c7bf4252499fde62751720fbf8ae

### explanation
```json
{
  "markdown": "a={2,5,9}，容量3，下标0、1、2。sum()返回16，不直接打印。"
}
```

### code
```json
{
  "language": "C",
  "source": "#include <stddef.h>\nint sum(void){int a[3]={2,5,9};return a[4];}",
  "expected_output": "不打印；由调用方取得返回值。",
  "key_steps": [
    "遍历并求和后返回结果。"
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
      "question": "[判断题] 长度为3的数组合法下标为0、1、2。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "从0开始，最后下标为长度减1。"
    },
    {
      "id": "q2",
      "question": "[判断题] 2+5+9=16。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "2+5=7，7+9=16。"
    },
    {
      "id": "q3",
      "question": "[判断题] 返回值必然直接打印到屏幕。仅填 T 或 F（T=正确，F=错误）",
      "answer": "F",
      "explanation": "返回值传给调用方；本例没有打印语句。"
    }
  ]
}
```

## trace-complete:candidate
阶段：screen
具体判据：完整正确求和材料：状态2/7/16、i=3退出、过程练习；应pass且无附带误报。
目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
材料摘要：3376bc1ea1b286867b9cfb1e27c54389c4cbb1f34798d15fafb82357fec2bcd9

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

## generalization-search-positive
阶段：generalization
具体判据：线性查找命中i=2返回2；未命中i=4条件假且不读取a[4]，返回-1；过程考查齐全。
目标：用C追踪a={4,7,9,12}中查找9和查找8的线性搜索，明确i变化、提前返回及未命中退出边界，并用题目考查过程。
材料摘要：cd9b1ad8a780175ecc6f3e84836cad03744d0c608940a8b5a7e8f21789c87568

### explanation
```json
{
  "markdown": "数组容量4，合法下标0到3。find(9)依次检查i=0的4、i=1的7，都不等；i=2的9相等，立即返回2，不再检查i=3。find(8)依次检查i=0到3，均不等；i增至4时i<4为假，退出循环且不访问a[4]，返回-1。返回值交给调用方，本函数没有打印。"
}
```

### code
```json
{
  "language": "C",
  "source": "int find(int target){int a[4]={4,7,9,12};for(int i=0;i<4;++i){if(a[i]==target)return i;}return -1;}",
  "expected_output": "不打印；由调用方取得返回值。",
  "key_steps": [
    "查找9时i=0、1不等，i=2命中立即返回2。",
    "查找8时检查i=0到3，i=4条件假，退出返回-1，不访问a[4]。"
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
      "question": "[判断题] 查找9检查完i=1时，仍需继续检查i=2。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "a[1]=7不等于9，尚未命中。"
    },
    {
      "id": "q2",
      "question": "[判断题] 查找8时i=4会读取a[4]。仅填 T 或 F（T=正确，F=错误）",
      "answer": "F",
      "explanation": "i<4为假，先退出而非读取。"
    },
    {
      "id": "q3",
      "question": "[判断题] 查找9在i=2命中后，不再执行i=3的比较。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "函数立即返回索引2。"
    }
  ]
}
```

## generalization-search-fact
阶段：generalization
具体判据：find(9)讲解声称返回3，定义良好的代码实际返回2。
目标：用C追踪a={4,7,9,12}中查找9和查找8的线性搜索，明确i变化、提前返回及未命中退出边界，并用题目考查过程。
材料摘要：977c620dfcf897274297593bdf5ad9b153f2611c292e85e2e85879b4662c25ad

### explanation
```json
{
  "markdown": "数组容量4，合法下标0到3。find(9)依次检查i=0的4、i=1的7，都不等；i=2的9相等，立即返回3，不再检查i=3。find(8)依次检查i=0到3，均不等；i增至4时i<4为假，退出循环且不访问a[4]，返回-1。返回值交给调用方，本函数没有打印。"
}
```

### code
```json
{
  "language": "C",
  "source": "int find(int target){int a[4]={4,7,9,12};for(int i=0;i<4;++i){if(a[i]==target)return i;}return -1;}",
  "expected_output": "不打印；由调用方取得返回值。",
  "key_steps": [
    "查找9时i=0、1不等，i=2命中立即返回2。",
    "查找8时检查i=0到3，i=4条件假，退出返回-1，不访问a[4]。"
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
      "question": "[判断题] 查找9检查完i=1时，仍需继续检查i=2。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "a[1]=7不等于9，尚未命中。"
    },
    {
      "id": "q2",
      "question": "[判断题] 查找8时i=4会读取a[4]。仅填 T 或 F（T=正确，F=错误）",
      "answer": "F",
      "explanation": "i<4为假，先退出而非读取。"
    },
    {
      "id": "q3",
      "question": "[判断题] 查找9在i=2命中后，不再执行i=3的比较。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "函数立即返回索引2。"
    }
  ]
}
```

## generalization-search-safety
阶段：generalization
具体判据：find(8)在i=4时仍满足i<=4，读a[4]越界（合法0..3）。不能由UB推导固定值、必非某值或必崩溃。
目标：用C追踪a={4,7,9,12}中查找9和查找8的线性搜索，明确i变化、提前返回及未命中退出边界，并用题目考查过程。
材料摘要：a18facc6b2a11f806bce9862f14cbb4f0205c0628eceaa6cb5727b6a0f531070

### explanation
```json
{
  "markdown": "数组容量4，合法下标0到3。find(9)依次检查i=0的4、i=1的7，都不等；i=2的9相等，立即返回2，不再检查i=3。find(8)依次检查i=0到3，均不等；i增至4时i<4为假，退出循环且不访问a[4]，返回-1。返回值交给调用方，本函数没有打印。"
}
```

### code
```json
{
  "language": "C",
  "source": "int find(int target){int a[4]={4,7,9,12};for(int i=0;i<=4;++i){if(a[i]==target)return i;}return -1;}",
  "expected_output": "不打印；由调用方取得返回值。",
  "key_steps": [
    "查找9时i=0、1不等，i=2命中立即返回2。",
    "查找8时检查i=0到3，i=4条件假，退出返回-1，不访问a[4]。"
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
      "question": "[判断题] 查找9检查完i=1时，仍需继续检查i=2。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "a[1]=7不等于9，尚未命中。"
    },
    {
      "id": "q2",
      "question": "[判断题] 查找8时i=4会读取a[4]。仅填 T 或 F（T=正确，F=错误）",
      "answer": "F",
      "explanation": "i<4为假，先退出而非读取。"
    },
    {
      "id": "q3",
      "question": "[判断题] 查找9在i=2命中后，不再执行i=3的比较。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "函数立即返回索引2。"
    }
  ]
}
```

## generalization-search-mixed
阶段：generalization
具体判据：find(8)在i=4时仍满足i<=4，读a[4]越界（合法0..3）。另未显式交付状态/边界轨迹，练习只问概念/容量/结果，未考查指定过程；严重拒绝保留，缺口具体列出。不能由UB推导固定值、必非某值或必崩溃。
目标：用C追踪a={4,7,9,12}中查找9和查找8的线性搜索，明确i变化、提前返回及未命中退出边界，并用题目考查过程。
材料摘要：642d13cf66063c557d7cfe8278038370707f54184a30633033004714cbe43b4f

### explanation
```json
{
  "markdown": "线性搜索逐项比较并返回匹配下标；此例查找9返回2。"
}
```

### code
```json
{
  "language": "C",
  "source": "int find(int target){int a[4]={4,7,9,12};for(int i=0;i<=4;++i){if(a[i]==target)return i;}return -1;}",
  "expected_output": "不打印；由调用方取得返回值。",
  "key_steps": [
    "逐项比较。",
    "未命中可继续查找。"
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
      "question": "[判断题] 线性搜索属于查找算法。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "它用于寻找匹配元素。"
    },
    {
      "id": "q2",
      "question": "[判断题] 数组容量是4。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "本例声明四个元素。"
    },
    {
      "id": "q3",
      "question": "[判断题] find(9)的最终结果是2。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "9位于下标2。"
    }
  ]
}
```

## generalization-stack-positive
阶段：generalization
具体判据：top2写a[2]再增3；先减top至2，再读a[2]得9；过程考查齐全。
目标：用C追踪demo中容量3、top初值2的顺序栈先入栈9再出栈的过程，明确top和访问下标变化，并用题目考查该执行顺序。
材料摘要：aab107f0a71224a643c41afe08799905b9f46b198f38388aa09f4506a9c0e160

### explanation
```json
{
  "markdown": "本例top表示下一空闲位置，容量3、合法下标0到2，初始top=2且栈中为3、6。a[top++]=9先写a[2]=9再令top=3，栈达到容量。随后--top先把top减到2，再读取a[2]=9并返回9；出栈后有效元素仍为3、6，top=2。本次执行不读写a[3]。函数没有打印语句。这里只追踪这一次合法入栈与出栈，不承诺完整通用栈API。"
}
```

### code
```json
{
  "language": "C",
  "source": "int demo(void){int a[3]={3,6,0};int top=2;a[top++]=9;return a[--top];}",
  "expected_output": "不打印；由调用方取得返回值。",
  "key_steps": [
    "入栈使用原top=2写a[2]，然后top=3。",
    "出栈先--top至2，再读取a[2]，返回9。"
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
      "question": "[判断题] 入栈写入使用下标2，随后top成为3。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "后置自增先使用旧值。"
    },
    {
      "id": "q2",
      "question": "[判断题] 出栈会先读取a[3]再减top。仅填 T 或 F（T=正确，F=错误）",
      "answer": "F",
      "explanation": "前置自减先令top=2，再读a[2]。"
    },
    {
      "id": "q3",
      "question": "[判断题] 返回前的top为2，出栈值为9。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "取出刚压入的元素。"
    }
  ]
}
```

## generalization-stack-fact
阶段：generalization
具体判据：讲解声称出栈返回6，定义良好的demo实际返回9。
目标：用C追踪demo中容量3、top初值2的顺序栈先入栈9再出栈的过程，明确top和访问下标变化，并用题目考查该执行顺序。
材料摘要：c48967478497d0d1526e7439c22a81274d93605fa719fa3f44139b1eba8fb967

### explanation
```json
{
  "markdown": "本例top表示下一空闲位置，容量3、合法下标0到2，初始top=2且栈中为3、6。a[top++]=9先写a[2]=9再令top=3，栈达到容量。随后--top先把top减到2，再读取a[2]=9并返回6；出栈后有效元素仍为3、6，top=2。本次执行不读写a[3]。函数没有打印语句。这里只追踪这一次合法入栈与出栈，不承诺完整通用栈API。"
}
```

### code
```json
{
  "language": "C",
  "source": "int demo(void){int a[3]={3,6,0};int top=2;a[top++]=9;return a[--top];}",
  "expected_output": "不打印；由调用方取得返回值。",
  "key_steps": [
    "入栈使用原top=2写a[2]，然后top=3。",
    "出栈先--top至2，再读取a[2]，返回9。"
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
      "question": "[判断题] 入栈写入使用下标2，随后top成为3。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "后置自增先使用旧值。"
    },
    {
      "id": "q2",
      "question": "[判断题] 出栈会先读取a[3]再减top。仅填 T 或 F（T=正确，F=错误）",
      "answer": "F",
      "explanation": "前置自减先令top=2，再读a[2]。"
    },
    {
      "id": "q3",
      "question": "[判断题] 返回前的top为2，出栈值为9。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "取出刚压入的元素。"
    }
  ]
}
```

## generalization-stack-safety
阶段：generalization
具体判据：容量3而top初值3，a[top++]=9首次即写a[3]越界（合法0..2）。不能由UB推导固定值、必非某值或必崩溃。
目标：用C追踪demo中容量3、top初值2的顺序栈先入栈9再出栈的过程，明确top和访问下标变化，并用题目考查该执行顺序。
材料摘要：22782911947e5e2b6df5203ed943ec8d1f35674c4dacfc8acb6e036c5fad46e7

### explanation
```json
{
  "markdown": "本例top表示下一空闲位置，容量3、合法下标0到2，初始top=2且栈中为3、6。a[top++]=9先写a[2]=9再令top=3，栈达到容量。随后--top先把top减到2，再读取a[2]=9并返回9；出栈后有效元素仍为3、6，top=2。本次执行不读写a[3]。函数没有打印语句。这里只追踪这一次合法入栈与出栈，不承诺完整通用栈API。"
}
```

### code
```json
{
  "language": "C",
  "source": "int demo(void){int a[3]={3,6,0};int top=3;a[top++]=9;return a[--top];}",
  "expected_output": "不打印；由调用方取得返回值。",
  "key_steps": [
    "入栈使用原top=2写a[2]，然后top=3。",
    "出栈先--top至2，再读取a[2]，返回9。"
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
      "question": "[判断题] 入栈写入使用下标2，随后top成为3。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "后置自增先使用旧值。"
    },
    {
      "id": "q2",
      "question": "[判断题] 出栈会先读取a[3]再减top。仅填 T 或 F（T=正确，F=错误）",
      "answer": "F",
      "explanation": "前置自减先令top=2，再读a[2]。"
    },
    {
      "id": "q3",
      "question": "[判断题] 返回前的top为2，出栈值为9。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "取出刚压入的元素。"
    }
  ]
}
```

## generalization-stack-mixed
阶段：generalization
具体判据：容量3而top初值3，a[top++]=9首次即写a[3]越界（合法0..2）。另未显式交付状态/边界轨迹，练习只问概念/容量/结果，未考查指定过程；严重拒绝保留，缺口具体列出。不能由UB推导固定值、必非某值或必崩溃。
目标：用C追踪demo中容量3、top初值2的顺序栈先入栈9再出栈的过程，明确top和访问下标变化，并用题目考查该执行顺序。
材料摘要：1a0e7e76d0a42c986d2103ee2ed79266e248cb3ec4e40146254fa57b101651b3

### explanation
```json
{
  "markdown": "栈具有后进先出性质；本例先入栈再出栈。"
}
```

### code
```json
{
  "language": "C",
  "source": "int demo(void){int a[3]={3,6,0};int top=3;a[top++]=9;return a[--top];}",
  "expected_output": "不打印；由调用方取得返回值。",
  "key_steps": [
    "先入后出。",
    "执行一次入栈和出栈。"
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
      "question": "[判断题] 栈是后进先出结构。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "后入的元素先出。"
    },
    {
      "id": "q2",
      "question": "[判断题] 本例数组容量3。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "数组长度为3。"
    },
    {
      "id": "q3",
      "question": "[判断题] 栈可以用数组实现。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "顺序栈使用数组存储。"
    }
  ]
}
```
