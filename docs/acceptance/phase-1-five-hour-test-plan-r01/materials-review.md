# 冻结材料阅读册（没有真实结果）

四个A项冻结完整输入，不预造实际课程；八个U和四个R项冻结完整学生材料。标签另见labels.json，实际调用结果均为null。所有内容由GPT编写/静态核对，沿用已知诊断结构，不是独立真人或双盲样本。

## A01

材料：[cases/A01.json](cases/A01.json)；canonical SHA256：`e8e3978ad6752718367360dd84826802847869ce324dceac4331d183b34e08bb`。

### 完整原始请求

用C实现数组{7,2,5}的求和，明确逐轮s和i、首次条件失败与不访问a[3]；给出讲解、完整可编译程序（含main调用）、恰好三道要求推演过程的题及答案解析，不要动画。

### 冻结输入上下文（实际输出尚不存在）

```json
{
  "metadata": {
    "node_id": "array",
    "graph_version": "mvp-0.2.0",
    "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
    "profile_version": null,
    "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
    "goal": "用C实现数组{7,2,5}的求和，明确逐轮s和i、首次条件失败与不访问a[3]；给出讲解、完整可编译程序（含main调用）、恰好三道要求推演过程的题及答案解析，不要动画。",
    "code_language": "C"
  },
  "references": {
    "graph-node:mvp-0.2.0:array": {
      "reference_id": "graph-node:mvp-0.2.0:array",
      "version": "mvp-0.2.0",
      "digest": "f83fd12e754fcda4124aa62b8a29203d97a897605d23dc4e37877393dcb0015d"
    }
  },
  "learner_evidence": {},
  "node_ids": [
    "array",
    "array-stack",
    "balanced-binary-search-tree",
    "binary-heap",
    "binary-search-tree",
    "binary-tree",
    "binary-tree-traversal",
    "breadth-first-search",
    "bubble-sort",
    "c-pointer",
    "circular-linked-list",
    "circular-queue",
    "depth-first-search",
    "doubly-linked-list",
    "graph-representation",
    "heap-sort",
    "insertion-sort",
    "linked-list-concept",
    "linked-list-deletion",
    "linked-list-insertion",
    "linked-list-traversal",
    "linked-stack",
    "merge-sort",
    "queue",
    "quick-sort",
    "selection-sort",
    "single-linked-list",
    "sorting-comparison",
    "stack",
    "tree-concept"
  ],
  "teaching_context": {
    "version": "teaching-node-binding-v1",
    "teaching_mode": "target",
    "target_node_id": "array",
    "recommended_node_id": "array",
    "teaching_node_id": "array",
    "selection_reason": "direct_target",
    "original_request": "用C实现数组{7,2,5}的求和，明确逐轮s和i、首次条件失败与不访问a[3]；给出讲解、完整可编译程序（含main调用）、恰好三道要求推演过程的题及答案解析，不要动画。",
    "segment_goal": "用C实现数组{7,2,5}的求和，明确逐轮s和i、首次条件失败与不访问a[3]；给出讲解、完整可编译程序（含main调用）、恰好三道要求推演过程的题及答案解析，不要动画。",
    "segment_scope": "target_lesson",
    "path_version_id": "f4522ea2-f4c7-5ed0-9c11-5a32ece7f4e1",
    "path_version": 1,
    "graph_version": "mvp-0.2.0",
    "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59"
  }
}
```

验收清单（非模型答案）：
- s:0→7→9→14；首次失败i=3；返回14与打印区分
- 三题实际要求过程知识，不能仅问7+2+5
## A02

材料：[cases/A02.json](cases/A02.json)；canonical SHA256：`5517984c4679d0ff59a29aa9611696cd43d4f0f359ee67d07f321d9212d5a83b`。

### 完整原始请求

主题是无头结点单链表头插法，C语言，空链表依次头插3和8。用int push_front(Node **head,int value)返回1成功/0失败；malloc失败不改变旧链表。提供讲解、含main和完整释放的可编译程序、恰好三道过程题及解析。指针和分配仅是配套要求，不另选教学主题；不需要动画。

### 冻结输入上下文（实际输出尚不存在）

```json
{
  "metadata": {
    "node_id": "linked-list-insertion",
    "graph_version": "mvp-0.2.0",
    "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
    "profile_version": null,
    "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
    "goal": "主题是无头结点单链表头插法，C语言，空链表依次头插3和8。用int push_front(Node **head,int value)返回1成功/0失败；malloc失败不改变旧链表。提供讲解、含main和完整释放的可编译程序、恰好三道过程题及解析。指针和分配仅是配套要求，不另选教学主题；不需要动画。",
    "code_language": "C"
  },
  "references": {
    "graph-node:mvp-0.2.0:linked-list-insertion": {
      "reference_id": "graph-node:mvp-0.2.0:linked-list-insertion",
      "version": "mvp-0.2.0",
      "digest": "b06b9a38c5be73059d9b542efa22a7ddfcb65913cbf036573a69b2b4dcd0ed98"
    }
  },
  "learner_evidence": {},
  "node_ids": [
    "array",
    "array-stack",
    "balanced-binary-search-tree",
    "binary-heap",
    "binary-search-tree",
    "binary-tree",
    "binary-tree-traversal",
    "breadth-first-search",
    "bubble-sort",
    "c-pointer",
    "circular-linked-list",
    "circular-queue",
    "depth-first-search",
    "doubly-linked-list",
    "graph-representation",
    "heap-sort",
    "insertion-sort",
    "linked-list-concept",
    "linked-list-deletion",
    "linked-list-insertion",
    "linked-list-traversal",
    "linked-stack",
    "merge-sort",
    "queue",
    "quick-sort",
    "selection-sort",
    "single-linked-list",
    "sorting-comparison",
    "stack",
    "tree-concept"
  ],
  "teaching_context": {
    "version": "teaching-node-binding-v1",
    "teaching_mode": "target",
    "target_node_id": "linked-list-insertion",
    "recommended_node_id": "linked-list-insertion",
    "teaching_node_id": "linked-list-insertion",
    "selection_reason": "direct_target",
    "original_request": "主题是无头结点单链表头插法，C语言，空链表依次头插3和8。用int push_front(Node **head,int value)返回1成功/0失败；malloc失败不改变旧链表。提供讲解、含main和完整释放的可编译程序、恰好三道过程题及解析。指针和分配仅是配套要求，不另选教学主题；不需要动画。",
    "segment_goal": "主题是无头结点单链表头插法，C语言，空链表依次头插3和8。用int push_front(Node **head,int value)返回1成功/0失败；malloc失败不改变旧链表。提供讲解、含main和完整释放的可编译程序、恰好三道过程题及解析。指针和分配仅是配套要求，不另选教学主题；不需要动画。",
    "segment_scope": "target_lesson",
    "path_version_id": "3d2bc4ab-6ccc-53e1-b728-a7500511c251",
    "path_version": 1,
    "graph_version": "mvp-0.2.0",
    "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59"
  }
}
```

验收清单（非模型答案）：
- 链表[]→[3]→[8,3]，首/次分配失败分别保持[]/[3]，不丢旧头
- malloc检查、next/头指针顺序、调用返回约定与完整释放正确；不得只凭局部NULL检查断言调用方安全
## A03

材料：[cases/A03.json](cases/A03.json)；canonical SHA256：`343e6189872630f1aab7c8cd276e162c37dd2a99741880551f6ab5f11116ad0c`。

### 完整原始请求

用C实现容量3、top表示元素数的数组栈，演示依次入栈4、11再出栈一次。提供讲解、含main的完整程序、恰好三道过程题及解析。明确空栈不读数组、满栈不写出容量，top与返回值的变化；不需要动画。

### 冻结输入上下文（实际输出尚不存在）

```json
{
  "metadata": {
    "node_id": "stack",
    "graph_version": "mvp-0.2.0",
    "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
    "profile_version": null,
    "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
    "goal": "用C实现容量3、top表示元素数的数组栈，演示依次入栈4、11再出栈一次。提供讲解、含main的完整程序、恰好三道过程题及解析。明确空栈不读数组、满栈不写出容量，top与返回值的变化；不需要动画。",
    "code_language": "C"
  },
  "references": {
    "graph-node:mvp-0.2.0:stack": {
      "reference_id": "graph-node:mvp-0.2.0:stack",
      "version": "mvp-0.2.0",
      "digest": "fcd31b8e716614bb18a06dcac7e20afbfb1fa4dccccc1871a6391bc96ce121b0"
    }
  },
  "learner_evidence": {},
  "node_ids": [
    "array",
    "array-stack",
    "balanced-binary-search-tree",
    "binary-heap",
    "binary-search-tree",
    "binary-tree",
    "binary-tree-traversal",
    "breadth-first-search",
    "bubble-sort",
    "c-pointer",
    "circular-linked-list",
    "circular-queue",
    "depth-first-search",
    "doubly-linked-list",
    "graph-representation",
    "heap-sort",
    "insertion-sort",
    "linked-list-concept",
    "linked-list-deletion",
    "linked-list-insertion",
    "linked-list-traversal",
    "linked-stack",
    "merge-sort",
    "queue",
    "quick-sort",
    "selection-sort",
    "single-linked-list",
    "sorting-comparison",
    "stack",
    "tree-concept"
  ],
  "teaching_context": {
    "version": "teaching-node-binding-v1",
    "teaching_mode": "target",
    "target_node_id": "stack",
    "recommended_node_id": "stack",
    "teaching_node_id": "stack",
    "selection_reason": "direct_target",
    "original_request": "用C实现容量3、top表示元素数的数组栈，演示依次入栈4、11再出栈一次。提供讲解、含main的完整程序、恰好三道过程题及解析。明确空栈不读数组、满栈不写出容量，top与返回值的变化；不需要动画。",
    "segment_goal": "用C实现容量3、top表示元素数的数组栈，演示依次入栈4、11再出栈一次。提供讲解、含main的完整程序、恰好三道过程题及解析。明确空栈不读数组、满栈不写出容量，top与返回值的变化；不需要动画。",
    "segment_scope": "target_lesson",
    "path_version_id": "e371c559-72bd-569d-89af-078f0930d636",
    "path_version": 1,
    "graph_version": "mvp-0.2.0",
    "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59"
  }
}
```

验收清单（非模型答案）：
- top:0→1→2→1，pop返回11，合法下标0..2
- 空/满检查和失败不改状态，先减后读或先读top-1再减均可，不虚构唯一合法形式
## A04

材料：[cases/A04.json](cases/A04.json)；canonical SHA256：`becb56b786d3ad8a3025d3a954c09378d38fa48d9046e2fb7e9f8f2b00ca3d8a`。

### 完整原始请求

用C实现容量4的循环队列，front指下一读取位置、rear指下一写入位置、size表示元素数，初始均0。入队5、9、11、13，出队一次，再入队17。提供讲解、含main完整程序、恰好三道过程题及解析；追踪回绕并以size区分空满，失败不改状态；无需动画。

### 冻结输入上下文（实际输出尚不存在）

```json
{
  "metadata": {
    "node_id": "circular-queue",
    "graph_version": "mvp-0.2.0",
    "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
    "profile_version": null,
    "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
    "goal": "用C实现容量4的循环队列，front指下一读取位置、rear指下一写入位置、size表示元素数，初始均0。入队5、9、11、13，出队一次，再入队17。提供讲解、含main完整程序、恰好三道过程题及解析；追踪回绕并以size区分空满，失败不改状态；无需动画。",
    "code_language": "C"
  },
  "references": {
    "graph-node:mvp-0.2.0:circular-queue": {
      "reference_id": "graph-node:mvp-0.2.0:circular-queue",
      "version": "mvp-0.2.0",
      "digest": "bae1a2d3b0ae7b45a1edfe13f67123c26886158c35bd2967b88a24fe64c5360a"
    }
  },
  "learner_evidence": {},
  "node_ids": [
    "array",
    "array-stack",
    "balanced-binary-search-tree",
    "binary-heap",
    "binary-search-tree",
    "binary-tree",
    "binary-tree-traversal",
    "breadth-first-search",
    "bubble-sort",
    "c-pointer",
    "circular-linked-list",
    "circular-queue",
    "depth-first-search",
    "doubly-linked-list",
    "graph-representation",
    "heap-sort",
    "insertion-sort",
    "linked-list-concept",
    "linked-list-deletion",
    "linked-list-insertion",
    "linked-list-traversal",
    "linked-stack",
    "merge-sort",
    "queue",
    "quick-sort",
    "selection-sort",
    "single-linked-list",
    "sorting-comparison",
    "stack",
    "tree-concept"
  ],
  "teaching_context": {
    "version": "teaching-node-binding-v1",
    "teaching_mode": "target",
    "target_node_id": "circular-queue",
    "recommended_node_id": "circular-queue",
    "teaching_node_id": "circular-queue",
    "selection_reason": "direct_target",
    "original_request": "用C实现容量4的循环队列，front指下一读取位置、rear指下一写入位置、size表示元素数，初始均0。入队5、9、11、13，出队一次，再入队17。提供讲解、含main完整程序、恰好三道过程题及解析；追踪回绕并以size区分空满，失败不改状态；无需动画。",
    "segment_goal": "用C实现容量4的循环队列，front指下一读取位置、rear指下一写入位置、size表示元素数，初始均0。入队5、9、11、13，出队一次，再入队17。提供讲解、含main完整程序、恰好三道过程题及解析；追踪回绕并以size区分空满，失败不改状态；无需动画。",
    "segment_scope": "target_lesson",
    "path_version_id": "e2c7d468-fa71-56bb-9cc7-b59b6aab01cf",
    "path_version": 1,
    "graph_version": "mvp-0.2.0",
    "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59"
  }
}
```

验收清单（非模型答案）：
- 首次四次入队后front0/rear0/size4；出队5后front1/size3；再入17后front1/rear1/size4
- 最终逻辑顺序9,11,13,17；空size0/满size4，front==rear不单独判空；所有下标取模4
## U01

材料：[cases/U01.json](cases/U01.json)；canonical SHA256：`ba215f92afab25af66bc2056707d80f1b4f0a4e6a25329eeeae815781608e411`。

原始请求：用C实现并明确追踪数组{4,6,9}求和的关键状态与循环退出条件，并用题目考查过程掌握。

实际教学目标：用C实现并明确追踪数组{4,6,9}求和的关键状态与循环退出条件，并用题目考查过程掌握。

审核scope：unit；完整三场景聚合审核。

### explanation

sum_sample返回17，无打印。初始s=0；i=0轮后s=4，i=1轮后s=10，i=2轮后s=19；随后i=3，3<3为假，退出，不访问a[3]，返回19，无打印。

### code

```c
int sum_sample(void) {
    int a[3] = {4, 6, 9};
    int s = 0;
    for (int i = 0; i < 3; ++i) s += a[i];
    return s;
}
```

函数返回19，没有标准输出。

关键步骤：
- 初始s=0；i=0轮后s=4，i=1轮后s=10，i=2轮后s=19；随后i=3，3<3为假，退出，不访问a[3]，返回19，无打印。

### exercise

**q1** [判断题] 请从s=0逐轮推演：i=1轮结束后s=10 仅填 T 或 F（T=正确，F=错误）。

答案：T

解析：先加4得4，再加6得10。

**q2** [判断题] 请推演首次条件失败：i=3时退出，不执行访问a[3]的循环体 仅填 T 或 F（T=正确，F=错误）。

答案：T

解析：i=2轮后s=19，i递增为3，3<3为假，因此退出。

**q3** [判断题] 函数会自行把19打印到屏幕 仅填 T 或 F（T=正确，F=错误）。

答案：F

解析：函数只有return，没有打印语句。

内部计划、绑定、完整上下文、来源及动作/锚点均在对应case JSON中。内部轨迹不算学生可见教学；所有新写C仅静态核对，未编译/执行。

## U02

材料：[cases/U02.json](cases/U02.json)；canonical SHA256：`2217d1764e2ecc3cafb26bcd2d9e1f1becc71261f3092a3503a82a9993180f56`。

原始请求：提供一个可直接调用且数组访问安全的固定读取函数，说明下标与返回约定。

实际教学目标：提供一个可直接调用且数组访问安全的固定读取函数，说明下标与返回约定。

审核scope：unit；完整三场景聚合审核。

### explanation

read_example是一个可直接调用的固定数组读取函数。本例声称其访问安全，函数无打印。

### code

```c
int read_example(void) {
    int a[2] = {5, 7};
    return a[2];
}
```

没有标准输出；函数尝试返回一个数组元素。

关键步骤：
- 声明a含两个元素，随后执行return表达式。

### exercise

**q1** [判断题] 声明int a[2]后合法元素下标为0和1 仅填 T 或 F（T=正确，F=错误）。

答案：T

解析：长度2的元素下标是0、1。

**q2** [判断题] int a[2]中的a[2]是可合法读取的第三个元素 仅填 T 或 F（T=正确，F=错误）。

答案：F

解析：第三个位置不属于这两个数组元素。

**q3** [判断题] read_example包含打印语句 仅填 T 或 F（T=正确，F=错误）。

答案：F

解析：函数只有数组声明和return。

内部计划、绑定、完整上下文、来源及动作/锚点均在对应case JSON中。内部轨迹不算学生可见教学；所有新写C仅静态核对，未编译/执行。

## U03

材料：[cases/U03.json](cases/U03.json)；canonical SHA256：`d569b5baf7030531b53832546c8a514e33e5fc105b35875d39061c17f19aa9a5`。

原始请求：用C实现并明确追踪数组{4,6,9}求和的关键状态与循环退出条件，并用题目考查过程掌握。

实际教学目标：用C实现并明确追踪数组{4,6,9}求和的关键状态与循环退出条件，并用题目考查过程掌握。

审核scope：unit；完整三场景聚合审核。

### explanation

本节处理数组{4,6,9}的求和过程，函数没有打印语句。

### code

```c
int sum_sample(void) {
    int a[3] = {4, 6, 9};
    return a[3];
}
```

无标准输出；函数尝试把值返回给调用方。

关键步骤：
- 按给定实现运行。

### exercise

**q1** [判断题] 4+6+9=19 仅填 T 或 F（T=正确，F=错误）。

答案：T

解析：4+6=10，10+9=19。

**q2** [判断题] 6+9+4=19 仅填 T 或 F（T=正确，F=错误）。

答案：T

解析：6+9=15，15+4=19。

**q3** [判断题] 9+4+6=20 仅填 T 或 F（T=正确，F=错误）。

答案：F

解析：9+4+6=19。

内部计划、绑定、完整上下文、来源及动作/锚点均在对应case JSON中。内部轨迹不算学生可见教学；所有新写C仅静态核对，未编译/执行。

## U04

材料：[cases/U04.json](cases/U04.json)；canonical SHA256：`1294a49d02398a20c8309363fa80f90178e32bf18fbf564043a186c1512982cf`。

原始请求：用C实现并明确追踪数组{4,6,9}求和的关键状态与循环退出条件，并用题目考查过程掌握。

实际教学目标：用C实现并明确追踪数组{4,6,9}求和的关键状态与循环退出条件，并用题目考查过程掌握。

审核scope：unit；完整三场景聚合审核。

### explanation

本节处理数组{4,6,9}的求和过程，函数没有打印语句。

### code

```c
int sum_sample(void) {
    int a[3] = {4, 6, 9};
    int s = 0;
    for (int i = 0; i < 3; ++i) s += a[i];
    return s;
}
```

函数返回19，没有标准输出。

关键步骤：
- 按给定实现运行。

### exercise

**q1** [判断题] 请从s=0逐轮推演：i=1轮结束后s=12 仅填 T 或 F（T=正确，F=错误）。

答案：F

解析：本题答案F，此处不提供展开的状态表或退出边界推演。

**q2** [判断题] 请推演首次条件失败：i=4时退出，不执行访问a[3]的循环体 仅填 T 或 F（T=正确，F=错误）。

答案：F

解析：本题答案F，此处不提供展开的状态表或退出边界推演。

**q3** [判断题] 函数会自行把19打印到屏幕 仅填 T 或 F（T=正确，F=错误）。

答案：F

解析：函数只有return，没有打印语句。

内部计划、绑定、完整上下文、来源及动作/锚点均在对应case JSON中。内部轨迹不算学生可见教学；所有新写C仅静态核对，未编译/执行。

## U05

材料：[cases/U05.json](cases/U05.json)；canonical SHA256：`5be729234c249bfca7ff7aeecb420438be96f168e992e5e54beea964a2507e83`。

原始请求：用C实现并明确追踪数组{4,6,9}求和的关键状态与循环退出条件，并用题目考查过程掌握。

实际教学目标：用C实现并明确追踪数组{4,6,9}求和的关键状态与循环退出条件，并用题目考查过程掌握。

审核scope：unit；完整三场景聚合审核。

### explanation

本节只实现并追踪这个求和示例，不承诺整个数组节点。初始s=0；i=0轮后s=4，i=1轮后s=10，i=2轮后s=19；随后i=3，3<3为假，退出，不访问a[3]，返回19，无打印。

### code

```c
int sum_sample(void) {
    int a[3] = {4, 6, 9};
    int s = 0;
    for (int i = 0; i < 3; ++i) s += a[i];
    return s;
}
```

函数返回19，没有标准输出。

关键步骤：
- 初始s=0；i=0轮后s=4，i=1轮后s=10，i=2轮后s=19；随后i=3，3<3为假，退出，不访问a[3]，返回19，无打印。

### exercise

**q1** [判断题] 4+6+9=19 仅填 T 或 F（T=正确，F=错误）。

答案：T

解析：4+6=10，10+9=19。

**q2** [判断题] 6+9+4=19 仅填 T 或 F（T=正确，F=错误）。

答案：T

解析：6+9=15，15+4=19。

**q3** [判断题] 9+4+6=20 仅填 T 或 F（T=正确，F=错误）。

答案：F

解析：9+4+6=19。

内部计划、绑定、完整上下文、来源及动作/锚点均在对应case JSON中。内部轨迹不算学生可见教学；所有新写C仅静态核对，未编译/执行。

## U06

材料：[cases/U06.json](cases/U06.json)；canonical SHA256：`f7924784ee38b1e810d4b4708a3cbfcbdbba00013795e8ab3ba3d4195474e940`。

原始请求：用C实现并明确追踪数组{4,6,9}求和的关键状态与循环退出条件，并用题目考查过程掌握。

实际教学目标：用C实现并明确追踪数组{4,6,9}求和的关键状态与循环退出条件，并用题目考查过程掌握。

审核scope：unit；完整三场景聚合审核。

### explanation

本节只实现并追踪这个求和示例，不承诺整个数组节点。初始s=0；i=0轮后s=4，i=1轮后s=10，i=2轮后s=19；随后i=3，3<3为假，退出，不访问a[3]，返回19，无打印。

### code

```c
int sum_sample(void) {
    int a[3] = {4, 6, 9};
    int s = 0;
    for (int i = 0; i < 3; ++i) s += a[i];
    return s;
}
```

函数返回19，没有标准输出。

关键步骤：
- 初始s=0；i=0轮后s=4，i=1轮后s=10，i=2轮后s=19；随后i=3，3<3为假，退出，不访问a[3]，返回19，无打印。

### exercise

**q1** [判断题] 请从s=0逐轮推演：i=1轮结束后s=10 仅填 T 或 F（T=正确，F=错误）。

答案：T

解析：先加4得4，再加6得10。

**q2** [判断题] 请推演首次条件失败：i=3时退出，不执行访问a[3]的循环体 仅填 T 或 F（T=正确，F=错误）。

答案：T

解析：i=2轮后s=19，i递增为3，3<3为假，因此退出。

**q3** [判断题] 函数会自行把19打印到屏幕 仅填 T 或 F（T=正确，F=错误）。

答案：F

解析：函数只有return，没有打印语句。

内部计划、绑定、完整上下文、来源及动作/锚点均在对应case JSON中。内部轨迹不算学生可见教学；所有新写C仅静态核对，未编译/执行。

## U07

材料：[cases/U07.json](cases/U07.json)；canonical SHA256：`a1440cce2a10bdbe39b12373421abaa4d1e6fb6ee4ad88714eb6deeac394848e`。

原始请求：用C实现并明确追踪数组{4,6,9}求和的关键状态与循环退出条件，并用题目考查过程掌握。

实际教学目标：用C实现并明确追踪数组{4,6,9}求和的关键状态与循环退出条件，并用题目考查过程掌握。

审核scope：unit；完整三场景聚合审核。

### explanation

sum_sample求和数组{4,6,9}，返回19，不打印；关键状态见代码步骤，退出边界见q2解析。

### code

```c
int sum_sample(void) {
    int a[3] = {4, 6, 9};
    int s = 0;
    for (int i = 0; i < 3; ++i) s += a[i];
    return s;
}
```

函数返回19，没有标准输出。

关键步骤：
- s从0开始，处理i=0、1、2后依次为4、10、19。
- 退出边界见q2解析。

### exercise

**q1** [判断题] 请从s=0逐轮推演：i=1轮结束后s=10 仅填 T 或 F（T=正确，F=错误）。

答案：T

解析：先加4得4，再加6得10。

**q2** [判断题] 请推演首次条件失败：i=3时退出，不执行访问a[3]的循环体 仅填 T 或 F（T=正确，F=错误）。

答案：T

解析：i=2轮后s=19，i递增为3，3<3为假，因此退出。

**q3** [判断题] 函数会自行把19打印到屏幕 仅填 T 或 F（T=正确，F=错误）。

答案：F

解析：函数只有return，没有打印语句。

内部计划、绑定、完整上下文、来源及动作/锚点均在对应case JSON中。内部轨迹不算学生可见教学；所有新写C仅静态核对，未编译/执行。

## U08

材料：[cases/U08.json](cases/U08.json)；canonical SHA256：`d88ac46a0dbfd3698a9361c2c9a05e77616882c8f4918ba78ef5e7befb78cde1`。

原始请求：用C学习单链表头插法。

实际教学目标：为学习链表插入，本节先学习路径推荐的C 指针。原目标尚待后续完成。

审核scope：unit；完整三场景聚合审核。

### explanation

p保存value的地址；value初始化为21，*p在value仍存活时读到21，返回21，不打印。本节只补指针先修，尚未交付链表头插法，原目标留待后续。

### code

```c
int pointer_sample(void) {
    int value = 21;
    int *p = &value;
    return *p;
}
```

函数返回21，没有标准输出。

关键步骤：
- 先取value地址，再在value存活期间解引用；返回的是int值，不是局部变量地址。

### exercise

**q1** [判断题] p保存value的地址 仅填 T 或 F（T=正确，F=错误）。

答案：T

解析：&value取地址。

**q2** [判断题] 这次*p读取21 仅填 T 或 F（T=正确，F=错误）。

答案：T

解析：读取发生在value存活期间，value初始化为21。

**q3** [判断题] 返回int值等于返回局部变量地址 仅填 T 或 F（T=正确，F=错误）。

答案：F

解析：这里返回的是*p的整数值。

内部计划、绑定、完整上下文、来源及动作/锚点均在对应case JSON中。内部轨迹不算学生可见教学；所有新写C仅静态核对，未编译/执行。

## R01

材料：[cases/R01.json](cases/R01.json)；canonical SHA256：`8a873900c25873b0717f7dc8934b3d54f9b49fba9101c65f135ae12bfb43f71d`。

原始请求：讲解场景仅解释数组长度与下标；代码场景给出求和实现，练习场景提供题目。

实际教学目标：讲解场景仅解释数组长度与下标；代码场景给出求和实现，练习场景提供题目。

审核scope：resource；本请求只提供explanation资源，不提供兄弟资源正文。

### explanation

C数组a[3]包含3个同类型元素，合法下标为0、1、2。后续代码场景给出求和实现，练习场景提供题目；本讲解只说明长度和下标。

内部计划、绑定、完整上下文、来源及动作/锚点均在对应case JSON中。内部轨迹不算学生可见教学；所有新写C仅静态核对，未编译/执行。

## R02

材料：[cases/R02.json](cases/R02.json)；canonical SHA256：`47ec4ed6689aa47ca4db98f308277683a51f56d1bacf35775254810a5d1e251d`。

原始请求：用通用易读语言讲解C指针的取地址、解引用和返回值，不对未提供的个人掌握度作判断。

实际教学目标：用通用易读语言讲解C指针的取地址、解引用和返回值，不对未提供的个人掌握度作判断。

审核scope：resource；本请求只提供explanation资源，不提供兄弟资源正文。

### explanation

p保存value的地址；value初始化为21，*p在value仍存活时读到21，返回21，不打印。

内部计划、绑定、完整上下文、来源及动作/锚点均在对应case JSON中。内部轨迹不算学生可见教学；所有新写C仅静态核对，未编译/执行。

## R03

材料：[cases/R03.json](cases/R03.json)；canonical SHA256：`ac8de10384a8f12bbfe53885f0419e97a0e931044db2de860177049b70fd77ba`。

原始请求：用固定数组的首元素读取函数展示下标0和返回值，接口与注释必须一致。

实际教学目标：用固定数组的首元素读取函数展示下标0和返回值，接口与注释必须一致。

审核scope：resource；本请求只提供code资源，不提供兄弟资源正文。

### code

```c
int first_sample(void) {
    int a[3] = {4, 6, 9};
    /* 返回最后一个元素9。 */
    return a[0];
}
```

返回首元素4，没有标准输出。

关键步骤：
- 读取合法下标0的元素，其值为4。

内部计划、绑定、完整上下文、来源及动作/锚点均在对应case JSON中。内部轨迹不算学生可见教学；所有新写C仅静态核对，未编译/执行。

## R04

材料：[cases/R04.json](cases/R04.json)；canonical SHA256：`aa25cd526054e7864ff4b405d054cfca210455fb62c676c7ea89d8dfd04fa0ca`。

原始请求：用三个判断题检查数组求和、合法下标以及返回与打印的区别。

实际教学目标：用三个判断题检查数组求和、合法下标以及返回与打印的区别。

审核scope：resource；本请求只提供exercise资源，不提供兄弟资源正文。

### exercise

**q1** [判断题] 4+6+9=19 仅填 T 或 F（T=正确，F=错误）。

答案：F

解析：4+6+9=19，因此题干命题成立，应答T。

**q2** [判断题] 数组声明int a[3]的合法下标包含3 仅填 T 或 F（T=正确，F=错误）。

答案：F

解析：合法下标只有0、1、2。

**q3** [判断题] 执行int f(void){return 19;}会打印19 仅填 T 或 F（T=正确，F=错误）。

答案：F

解析：return把值交给调用方，不是打印。

内部计划、绑定、完整上下文、来源及动作/锚点均在对应case JSON中。内部轨迹不算学生可见教学；所有新写C仅静态核对，未编译/执行。
