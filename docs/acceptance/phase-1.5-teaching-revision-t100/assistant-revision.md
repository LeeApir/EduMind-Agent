# 中文教学修订草稿（助手离线修订）

这是对 T095 模型原稿的一次助手文字修订，不是模型重新生成，也不是审核或质量签核。代码、答案、事实引用和动作沿用原候选；原始候选保持不变。

## 讲解

本例演示单链表头插：初始结点 i0 的值为 9，依次插入 1 和 2。这里假定两次实际分配都成功；规格中的成功标记只允许调用 malloc，并不保证真实分配成功。i0 是初始的栈上结点，t0、t1 是两次新结点的轨迹标签，并不是代码中的变量名。

第一次调用先分配 t0；其 data 和 next 在写入前未知。随后把 data 设为 1，再令 p-&gt;next 指向原头 i0。函数返回 p，调用者接回后链表为 t0 → i0 → NULL。函数返回后，其局部变量已离开作用域。

第二次调用在成功分配 t1 后，将 data 设为 2，令 p-&gt;next 指向当前头 t0，再返回 p。调用者接回返回值，因此头变为 t1，链表为 t1 → t0 → i0 → NULL。

从调用者头出发依次得到 2、1、9，观察到 NULL 后终止，因此本例的可知前缀也是完整遍历结果，且两次合成分配失败数为 0。若遇到环或未知 next，只能报告重复或未知之前的可知前缀，不能声称有限的完整遍历。本轨迹只展示两次成功路径，没有单独高亮判空行，也没有演示失败分支或释放内存。动态结点不再使用时应安全释放；栈上的 i0 不可 free。对环或未知链接不能未经验证地套用释放过程。

## 代码

```c
#include <stdlib.h>
typedef struct Node { int data; struct Node *next; } Node;
Node *insert(Node *head, int value, int allocation_success) {
    Node *p = allocation_success ? malloc(sizeof *p) : NULL;
    if (p == NULL) return head;
    p->data = value;
    p->next = head;
    return p;
}
int main(void) {
    Node i0;
    i0.data = 9;
    i0.next = NULL;
    Node *caller_head = &i0;
    caller_head = insert(caller_head, 1, 1);
    caller_head = insert(caller_head, 2, 1);
    (void)caller_head;
    return 0;
}
```

## 第 1 题

两次插入后，调用者头指向哪个轨迹结点 ID？空指针用 none 表示。

参考答案：`"t1"`

第二次成功调用返回新结点，调用者接回该返回值，因此为 t1。

## 第 2 题

从最终调用者头开始遍历属于哪类？请使用 terminated（终止）、cycle（成环）或 indeterminate（未知）回答。

参考答案：`"terminated"`

依次经过 t1、t0 和 i0 后到达 NULL，因此为 terminated。

## 第 3 题

从最终调用者头开始，在重复或未知指针之前可知的整数值前缀是什么？

参考答案：`[2, 1, 9]`

依次是 2、1、9。本例继续观察到 NULL，因此这一前缀同时是本例完整遍历结果。

## 第 4 题

这份合成规格中有几次分配失败？

参考答案：`0`

本例假定两次分配都成功，因此合成分配失败次数为 0；真实 malloc 仍可能失败。

## 轨迹与动作

共享代码、状态、答案与动作字节未改；可对照 [原候选播放器](../phase-1.5-real-candidate-player-t098/course.html) 的同一段代码和动作。该播放器展示的是旧英文原文，不能当成此修订文本的播放器。

原候选及模型输出见 [T095 结果](../phase-1.5-combined-candidate-r01/results/RESULTS.md)。
