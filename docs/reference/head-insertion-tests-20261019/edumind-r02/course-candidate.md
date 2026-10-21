# 单链表头插法：完整课程候选（尚待人工复核）

这是封存原件后的派生阅读稿，未修改生成内容；完整结构、计划、引用和动作以 complete-review-case.json 为准。以下内容尚未发布，不构成人工签核。

# 单链表头插法

## 三个基本概念

- **节点 (node)**：由数据域 `data` 和指针域 `next` 组成的结构体变量，是链表的基本单元。
- **头指针 (head)**：指向链表第一个节点的指针。头指针本身不是节点；当 `head == NULL` 时，链表为空。
- **头插法 (head insertion)**：每次把新节点插到链表最前端，使它成为新的第一个节点，并让 `head` 指向它。

空链表写作：

```
head -> NULL
```

## 头插法的核心两步

设新节点为 `new_node`，头插法只需两步：

```c
new_node->next = head;  /* 新节点接到原链表前面 */
head = new_node;        /* 头指针改指向新节点 */
```

顺序不能颠倒：必须先让新节点接上原链表，再移动 `head`，否则原链表会丢失。

## 用同一个例子走一遍

从空链表 `head -> NULL` 开始，依次头插 1、2、3。

**插入 1**：`new_node->next = head`（即 NULL），`head = new_node`。

```
head -> [1] -> NULL
```

**插入 2**：`new_node->next = head`（指向 [1]），`head = new_node`。

```
head -> [2] -> [1] -> NULL
```

**插入 3**：`new_node->next = head`（指向 [2]），`head = new_node`。

```
head -> [3] -> [2] -> [1] -> NULL
```

**遍历**：`p = head`，沿 `next` 依次打印，得到输出 `3 2 1`。

**释放**：`p = head`，循环中先保存 `next`，再 `free(p)`，最后 `head = NULL`。

## 为什么输出顺序与插入顺序相反

头插法每次都把新节点放在最前面，所以最后插入的节点离 `head` 最近，遍历时最先被访问。插入顺序是 1、2、3，遍历顺序就是 3、2、1。

## 小结

- 头指针指向第一个节点，空链表用 `NULL` 表示。
- 头插法固定两步：先 `new_node->next = head`，再 `head = new_node`。
- 头插法得到的链表顺序与插入顺序相反。

## 完整 C 程序

```c
#include <stdio.h>
#include <stdlib.h>

/* 节点：数据域 data + 指针域 next */
typedef struct Node {
    int data;
    struct Node *next;
} Node;

/* 头插法：把 data 放入新节点，插到链表最前端，返回新的头指针 */
Node *insert_head(Node *head, int data)
{
    Node *new_node = (Node *)malloc(sizeof(Node));
    if (new_node == NULL) {
        return head; /* 分配失败，保持原链表不变 */
    }
    new_node->data = data;
    new_node->next = head; /* 第一步：新节点接到原链表前面 */
    head = new_node;       /* 第二步：头指针改指向新节点 */
    return head;
}

/* 遍历：从 head 出发沿 next 依次打印，直到 NULL */
void print_list(Node *head)
{
    Node *p = head;
    while (p != NULL) {
        printf("%d ", p->data);
        p = p->next;
    }
    printf("\n");
}

/* 释放：先保存 next，再 free 当前节点，最后 head 置为 NULL */
void free_list(Node *head)
{
    Node *p = head;
    while (p != NULL) {
        Node *next = p->next;
        free(p);
        p = next;
    }
}

int main(void)
{
    Node *head = NULL; /* 空链表：head -> NULL */

    head = insert_head(head, 1); /* head -> [1] -> NULL */
    head = insert_head(head, 2); /* head -> [2] -> [1] -> NULL */
    head = insert_head(head, 3); /* head -> [3] -> [2] -> [1] -> NULL */

    print_list(head); /* 输出：3 2 1 */

    free_list(head);
    head = NULL; /* 释放后置空，避免悬空指针 */

    return 0;
}
```

## 代码场景的关键步骤

1. 定义节点结构体 Node：data 存数据，next 指向后继节点；main 中 head = NULL 表示空链表 head -> NULL。

2. insert_head 中先 malloc 新节点并写入 data，再执行 new_node->next = head，把新节点接到原链表前面。

3. 紧接着执行 head = new_node，让头指针指向新节点；两步顺序不能颠倒，否则原链表会丢失。

4. 依次头插 1、2、3，链表状态依次变为 head -> [1] -> NULL、head -> [2] -> [1] -> NULL、head -> [3] -> [2] -> [1] -> NULL。

5. print_list 用游标 p = head 沿 next 遍历打印，得到 3 2 1，因为最后插入的节点离 head 最近。

6. free_list 循环中先保存 next 再 free(p)，最后 head = NULL，释放全部节点。

## 代码场景的预期输出

```text
3 2 1
```

## 三道练习、答案与解析

### q1

[单选题] 在头插法中，设 new_node 为新节点、head 为头指针，下列哪组语句顺序正确？
A. head = new_node; new_node->next = head;
B. new_node->next = head; head = new_node;
C. new_node->next = NULL; head = new_node->next;
D. head->next = new_node; head = new_node;
仅填 A、B、C 或 D

答案：B

解析：必须先让新节点的 next 指向原链表（new_node->next = head），再让 head 指向新节点。若先执行 head = new_node，原链表的头就丢失了。

### q2

[判断题] 从空链表 head -> NULL 开始，依次用头插法插入 1、2、3，遍历打印得到的输出是 3 2 1。仅填 T 或 F（T=正确，F=错误）

答案：T

解析：头插法每次把新节点放在最前面，最终链表为 head -> [3] -> [2] -> [1] -> NULL，遍历顺序是 3 2 1，与插入顺序相反。

### q3

[单选题] 从空链表 head -> NULL 开始，依次用头插法插入 1、2、3 后，head 指向的节点数据域是什么？
A. 1
B. 2
C. 3
D. NULL
仅填 A、B、C 或 D

答案：C

解析：头插法使最后插入的节点成为第一个节点，因此 head 指向数据为 3 的节点，链表为 head -> [3] -> [2] -> [1] -> NULL。

## 完整共享计划

```json
{
  "goal": "请为刚学完结构体和指针的 C 语言初学者，生成一节“单链表头插法”微课。\n\n内容包括：\n1. 解释头指针、节点以及头插法的执行过程。\n2. 提供完整、可编译的 C 程序，包括节点结构、头插函数、遍历函数、释放链表函数和 main。\n3. main 从空链表开始，依次插入 1、2、3，打印最终链表，最后释放资源。\n4. 逐步解释关键指针变化，并给出预期输出。\n5. 提供三道检查学生理解情况的练习，附答案和解析。\n\n讲解、代码、执行步骤和练习应使用同一个示例。",
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "depends_on": [],
      "objective_ids": [
        "obj-head-pointer",
        "obj-head-insert-trace",
        "obj-predict-output"
      ]
    },
    {
      "role": "code",
      "scene_key": "code",
      "depends_on": [
        "explanation"
      ],
      "objective_ids": [
        "obj-code-read",
        "obj-head-insert-trace"
      ]
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "depends_on": [
        "explanation",
        "code"
      ],
      "objective_ids": [
        "obj-exercise-apply",
        "obj-predict-output",
        "obj-head-insert-trace"
      ]
    }
  ],
  "node_id": "c-pointer",
  "objectives": [
    {
      "id": "obj-head-pointer",
      "text": "说明头指针、节点与空链表三者的关系，并能用 NULL 表示空链表。"
    },
    {
      "id": "obj-head-insert-trace",
      "text": "逐步追踪头插法中 head 与 next 指针的变化，写出每一步后的链表状态。"
    },
    {
      "id": "obj-code-read",
      "text": "读懂并解释包含节点结构、头插函数、遍历函数、释放函数和 main 的完整 C 程序。"
    },
    {
      "id": "obj-predict-output",
      "text": "根据头插顺序预测遍历输出，并解释为何输出顺序与插入顺序相反。"
    },
    {
      "id": "obj-exercise-apply",
      "text": "独立完成三道头插法相关练习，并说明答案依据。"
    }
  ],
  "references": [
    {
      "digest": "038e80d56854aedbfc8a65e828b514eb532ebfea54abf7b933ebfe79f8b0dfdc",
      "version": "mvp-0.2.0",
      "reference_id": "graph-node:mvp-0.2.0:c-pointer"
    }
  ],
  "conventions": {
    "capacity": null,
    "index_base": 0,
    "state_representation": "链表状态写作 head -> [d1] -> [d2] -> ... -> NULL，方括号内为节点数据域；空链表写作 head -> NULL。指针变量用 p 表示游标，new_node 表示新节点。",
    "not_applicable_reasons": [
      "链表为动态结构，无固定容量，故 capacity 不适用。",
      "节点按插入顺序编号时从 0 开始计位置，但链表本身不依赖下标访问。"
    ]
  },
  "terminology": [
    {
      "term": "节点 (node)",
      "meaning": "由数据域 data 和指针域 next 组成的结构体变量，是链表的基本单元。"
    },
    {
      "term": "头指针 (head)",
      "meaning": "指向链表第一个节点的指针；链表为空时其值为 NULL。头指针本身不是节点。"
    },
    {
      "term": "头插法 (head insertion)",
      "meaning": "每次把新节点插入到链表最前端，使新节点成为新的第一个节点，并让 head 指向它。"
    },
    {
      "term": "next 指针",
      "meaning": "节点中指向其后继节点的指针；尾节点的 next 为 NULL。"
    },
    {
      "term": "空链表",
      "meaning": "head == NULL 的链表，不含任何节点。"
    },
    {
      "term": "遍历 (traversal)",
      "meaning": "用游标指针从 head 出发沿 next 依次访问每个节点，直到遇到 NULL。"
    },
    {
      "term": "释放链表",
      "meaning": "从 head 开始逐个 free 节点，每次先保存 next 再释放当前节点，最后把 head 置为 NULL。"
    }
  ],
  "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
  "code_language": "C",
  "graph_version": "mvp-0.2.0",
  "schema_version": "learning-plan-v1",
  "shared_example": {
    "steps": [
      {
        "operation": "创建新节点 new_node，data=1，next=NULL；执行 new_node->next = head; head = new_node;",
        "expected_state": "head -> [1] -> NULL",
        "expected_output": null
      },
      {
        "operation": "创建新节点 new_node，data=2，next=NULL；执行 new_node->next = head; head = new_node;",
        "expected_state": "head -> [2] -> [1] -> NULL",
        "expected_output": null
      },
      {
        "operation": "创建新节点 new_node，data=3，next=NULL；执行 new_node->next = head; head = new_node;",
        "expected_state": "head -> [3] -> [2] -> [1] -> NULL",
        "expected_output": null
      },
      {
        "operation": "遍历：p = head，沿 next 依次打印各节点 data",
        "expected_state": "head -> [3] -> [2] -> [1] -> NULL（不变）",
        "expected_output": "3 2 1"
      },
      {
        "operation": "释放：p = head，循环中先保存 next，再 free(p)，最后 head = NULL",
        "expected_state": "head -> NULL",
        "expected_output": null
      }
    ],
    "initial_state": "head -> NULL（空链表）",
    "input_description": "从空链表开始，依次用头插法插入数据 1、2、3，然后遍历打印，最后释放链表。"
  },
  "profile_version": 1,
  "prerequisite_node_ids": [
    "c-pointer",
    "linked-list-concept"
  ],
  "profile_evidence_digest": "3d0244ecce85c5ca57944ed0a0f51619f7e06d321ce0499bbf242979af7a972e"
}
```

## 完整教学动作与锚点

```json
{
  "digest": "ee1b9e3766582fa54a2d0708117864a91f73bac81375e505a20ef35b8372d593",
  "actions": [
    {
      "kind": "show_resource",
      "scene_key": "explanation",
      "resource_id": "572fc9c4-ab91-44ce-83b1-c6c55890e2ae",
      "resource_digest": "7db528ad61c4564d05901374d04aa69665a1547b4eca596d3b8dfd03b9781965"
    },
    {
      "kind": "show_resource",
      "scene_key": "code",
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "kind": "highlight",
      "anchor_id": "a3",
      "scene_key": "code",
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "kind": "highlight",
      "anchor_id": "a4",
      "scene_key": "code",
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "kind": "highlight",
      "anchor_id": "a5",
      "scene_key": "code",
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "kind": "highlight",
      "anchor_id": "a6",
      "scene_key": "code",
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "kind": "highlight",
      "anchor_id": "a7",
      "scene_key": "code",
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "kind": "highlight",
      "anchor_id": "a8",
      "scene_key": "code",
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "kind": "show_resource",
      "scene_key": "exercise",
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "exercise_id": "q1",
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "exercise_id": "q2",
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "exercise_id": "q3",
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    }
  ],
  "version": "teaching-actions-v1",
  "anchor_catalog": [
    {
      "end_utf8": 1855,
      "anchor_id": "a1",
      "start_utf8": 0,
      "resource_id": "572fc9c4-ab91-44ce-83b1-c6c55890e2ae",
      "json_pointer": "/markdown",
      "resource_digest": "7db528ad61c4564d05901374d04aa69665a1547b4eca596d3b8dfd03b9781965"
    },
    {
      "end_utf8": 5,
      "anchor_id": "a2",
      "start_utf8": 0,
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "json_pointer": "/expected_output",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "end_utf8": 124,
      "anchor_id": "a3",
      "start_utf8": 0,
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "json_pointer": "/key_steps/0",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "end_utf8": 122,
      "anchor_id": "a4",
      "start_utf8": 0,
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "json_pointer": "/key_steps/1",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "end_utf8": 118,
      "anchor_id": "a5",
      "start_utf8": 0,
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "json_pointer": "/key_steps/2",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "end_utf8": 137,
      "anchor_id": "a6",
      "start_utf8": 0,
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "json_pointer": "/key_steps/3",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "end_utf8": 114,
      "anchor_id": "a7",
      "start_utf8": 0,
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "json_pointer": "/key_steps/4",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "end_utf8": 90,
      "anchor_id": "a8",
      "start_utf8": 0,
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "json_pointer": "/key_steps/5",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "end_utf8": 1,
      "anchor_id": "a9",
      "start_utf8": 0,
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "json_pointer": "/language",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "end_utf8": 1492,
      "anchor_id": "a10",
      "start_utf8": 0,
      "resource_id": "a2be40af-913d-4dff-bb28-b0805051b7e0",
      "json_pointer": "/source",
      "resource_digest": "6843211c5430f3a4e60a5a496522cdab0ba17eb4d8782a7ef3269e8ba98b83b5"
    },
    {
      "end_utf8": 1,
      "anchor_id": "a11",
      "start_utf8": 0,
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "json_pointer": "/items/0/answer",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    },
    {
      "end_utf8": 166,
      "anchor_id": "a12",
      "start_utf8": 0,
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "json_pointer": "/items/0/explanation",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    },
    {
      "end_utf8": 2,
      "anchor_id": "a13",
      "start_utf8": 0,
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "json_pointer": "/items/0/id",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    },
    {
      "end_utf8": 312,
      "anchor_id": "a14",
      "start_utf8": 0,
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "json_pointer": "/items/0/question",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    },
    {
      "end_utf8": 1,
      "anchor_id": "a15",
      "start_utf8": 0,
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "json_pointer": "/items/1/answer",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    },
    {
      "end_utf8": 145,
      "anchor_id": "a16",
      "start_utf8": 0,
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "json_pointer": "/items/1/explanation",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    },
    {
      "end_utf8": 2,
      "anchor_id": "a17",
      "start_utf8": 0,
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "json_pointer": "/items/1/id",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    },
    {
      "end_utf8": 162,
      "anchor_id": "a18",
      "start_utf8": 0,
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "json_pointer": "/items/1/question",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    },
    {
      "end_utf8": 1,
      "anchor_id": "a19",
      "start_utf8": 0,
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "json_pointer": "/items/2/answer",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    },
    {
      "end_utf8": 145,
      "anchor_id": "a20",
      "start_utf8": 0,
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "json_pointer": "/items/2/explanation",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    },
    {
      "end_utf8": 2,
      "anchor_id": "a21",
      "start_utf8": 0,
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "json_pointer": "/items/2/id",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    },
    {
      "end_utf8": 175,
      "anchor_id": "a22",
      "start_utf8": 0,
      "resource_id": "af890c08-60b7-4bb0-a9eb-64858115ab71",
      "json_pointer": "/items/2/question",
      "resource_digest": "5d959c9336be4313af5e576baded1eeda62b6d1d1f0db582bbcb44457bbf857d"
    }
  ]
}
```
