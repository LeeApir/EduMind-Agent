## 1. 从结构体与指针到链表

Type: slide

Element: text_Jj5gBJdc

```text
从结构体与指针到链表
```

Element: text_F8ROIING

```text
节点（node）结构 · 头指针（head pointer） · 头插法（head insertion）
```

Element: text_StltfQHM

```text
struct Node {
    int data;
    struct Node *next;
};
```

Element: text_ZmQDczCF

```text
• 节点 = data + next（数据域 + 指针域）
• head 指向第一个节点，空表时 head = NULL
• next 存下一个节点地址，节点不必连续
• 本课示例：空表依次插入 1、2、3
```

Element: text_YdVdfUsD

```text
头插法：新节点插到最前面，再让 head 指向它
示例：空链表 → 插入 1 → 插入 2 → 插入 3，得到 head → 3 → 2 → 1 → NULL
```

### 授课动作

```json
[
  {
    "id": "action_tK_NPms-",
    "type": "speech",
    "text": "大家好，欢迎来到今天的 C 语言课。前面我们已经把结构体和指针分别学完了，这节课就把这两样东西合起来，做出第一个真正有实用价值的数据结构——链表（linked list）。先看一下这节课的整体路线。"
  },
  {
    "id": "action_u1BmfFUp",
    "type": "spotlight",
    "elementId": "text_Jj5gBJdc"
  },
  {
    "id": "action_tgCX4h2o",
    "type": "speech",
    "text": "标题就是我们的起点：从结构体与指针到链表。整节课我会只用一个例子贯穿始终——从空链表开始，依次插入 1、2、3，后面所有的代码、指针变化步骤和练习，全都对得上这一个例子，请大家不要走神去记别的数据。"
  },
  {
    "id": "action_ZU1ClyHh",
    "type": "spotlight",
    "elementId": "text_StltfQHM"
  },
  {
    "id": "action_yeruwmcf",
    "type": "speech",
    "text": "先看最基础的一块：节点（node）。一个节点由两部分组成，数据域 data 存我们真正关心的值，指针域 next 存下一个节点的地址。写法上就是 struct Node 里面放一个 int data，再放一个 struct Node *next，注意这里写的是 struct Node 的指针，也就是指向自己这种类型的指针，这是链表能串起来的关键。"
  },
  {
    "id": "action_80g_AaiP",
    "type": "spotlight",
    "elementId": "text_ZmQDczCF"
  },
  {
    "id": "action_i4f5pHJO",
    "type": "speech",
    "text": "把这块记成三句话就够了：第一，节点等于 data 加 next，数据域加指针域；第二，头指针（head pointer）永远指向链表的第一个节点，如果链表是空的，那 head 就等于 NULL；第三，next 保存的是下一个节点的地址，所以这些节点在内存里不必连续，可以分散在任意位置，靠指针一个个连起来。"
  },
  {
    "id": "action_CQkzqaGF",
    "type": "spotlight",
    "elementId": "text_YdVdfUsD"
  },
  {
    "id": "action_4wWoD4hB",
    "type": "speech",
    "text": "那怎么把一个新节点放进链表里呢？今天先看最省事的做法——头插法（head insertion），一句话概括：新节点插到最前面，再让 head 指向它。听起来很简单，但赋值顺序一旦写反，链表就可能断开甚至整个丢失，这正是我们接下来几页要一步步拆开看的地方。"
  }
]
```

## 2. 头插法的三步执行过程

Type: slide

Element: text_Pg9fADKn

```text
头插法的三步执行过程
```

Element: text_HAfBreYU

```text
1
```

Element: text_xmfijM_N

```text
2
```

Element: text_WLvxey7v

```text
3
```

Element: text_s5-F1qWW

```text
第 1 步：申请新节点并写入数据
```

Element: text_BN6TxnFr

```text
newNode->data = value;
```

Element: text_NTZBsMdj

```text
第 2 步：新节点先接上原链表
```

Element: text_ZDeteY_m

```text
newNode->next = head;
```

Element: text_9dCmeqiZ

```text
第 3 步：头指针前移成为新头
```

Element: text_cdihRNUO

```text
head = newNode;
```

Element: text_mEM_FwbB

```text
注意：两步赋值顺序不可颠倒 —— 若先 head = newNode，原链表入口丢失，造成内存泄漏
```

Element: text_8cN327xT

```text
空链表
head → NULL
```

Element: text_07nF2DLe

```text
插入 1 后
head → 1 → NULL
```

Element: text_ElcbkjeC

```text
插入 2 后
head → 2 → 1 → NULL
```

Element: text_RVXqpp_o

```text
插入 3 后
head → 3 → 2 → 1 → NULL
```

### 授课动作

```json
[
  {
    "id": "action_JCrLAGv1",
    "type": "spotlight",
    "elementId": "text_Pg9fADKn"
  },
  {
    "id": "action_KJ5aFclQ",
    "type": "speech",
    "text": "上一页我们说过，头插法（head insertion）一句话就能概括：新节点插到最前面，再让 head 指向它。但这句话放到代码里，其实是三个固定动作，顺序一个都不能错。下面我们一步一步地拆开来看。"
  },
  {
    "id": "action_8WBqaoX_",
    "type": "spotlight",
    "elementId": "text_s5-F1qWW"
  },
  {
    "id": "action_tZTKTVHl",
    "type": "speech",
    "text": "第 1 步，申请新节点并写入数据。用 malloc 向内存申请一块空间，让 newNode 指向这块空间，接着写 newNode->data = value，把要插入的数据装进去。注意，这时新节点还是一个与链表无关的节点，它的 next 是随机值，链表完全不知道它的存在。"
  },
  {
    "id": "action_kq2sEczS",
    "type": "spotlight",
    "elementId": "text_NTZBsMdj"
  },
  {
    "id": "action_00S0uqcM",
    "type": "speech",
    "text": "第 2 步，让新节点先接到原来的链表上。执行 newNode->next = head，新节点的 next 就指向了原来链表的第一个节点。如果原链表是空的，head 就是 NULL，那么 newNode->next 得到的就是 NULL，正好表示这个新节点就是链表末尾。做完这一步，新节点已经接入原链表了，但 head 仍然指向旧的头节点。"
  },
  {
    "id": "action_qsSY2mfW",
    "type": "spotlight",
    "elementId": "text_9dCmeqiZ"
  },
  {
    "id": "action_x0Bd6mLG",
    "type": "speech",
    "text": "第 3 步，头指针前移。执行 head = newNode，让 head 改为指向新节点，新节点就正式成为链表新的头（head）。到这一步，三个动作才全部完成。"
  },
  {
    "id": "action_hai9yqYJ",
    "type": "spotlight",
    "elementId": "text_mEM_FwbB"
  },
  {
    "id": "action_zCsfMLMm",
    "type": "speech",
    "text": "这里有一个必须记住的注意事项：第 2 步和第 3 步这两条赋值语句的顺序不可颠倒。如果先写 head = newNode，head 立刻就指向了新节点，原来那条链表的入口就丢失了，后面的节点再也找不到，也 free 不掉，于是造成内存泄漏。所以口诀是：先接上旧链，再移动 head。"
  },
  {
    "id": "action_a8ZiKEJx",
    "type": "spotlight",
    "elementId": "text_8cN327xT"
  },
  {
    "id": "action_6faZYYsM",
    "type": "speech",
    "text": "我们用同一组数据走一遍。一开始链表是空的，head 就是 NULL。现在插入数据 1：新节点的 next 接到 NULL，head 指向 1，于是 head → 1 → NULL。"
  },
  {
    "id": "action_JflN4-Jj",
    "type": "spotlight",
    "elementId": "text_RVXqpp_o"
  },
  {
    "id": "action_w4LbJABK",
    "type": "speech",
    "text": "再插入 2，就变成 head → 2 → 1 → NULL；再插入 3，变成 head → 3 → 2 → 1 → NULL。你可以看到，每插一次，head 就往左移动一个位置，最新插入的永远排在最前面，这就是头插法的特点。记住这三步：先建节点、再接到旧链、最后移动 head，顺序就是关键。下一页我们就用图示一格一格地看指针到底是怎么变化的。"
  }
]
```

## 3. 指针变化可视化：单步看头插

Type: interactive

完整交互HTML见 original-interactive.html；原始定义见 original-manifest.json。

### 授课动作

```json
[
  {
    "id": "action_YKxsN2b8",
    "type": "speech",
    "text": "上一页我们看到 head 一次次往左移，那只是结果。这一页换个角度：把代码展开，一行一行单步执行，看看每个指针究竟在哪一刻改变了指向。"
  },
  {
    "id": "action_uxo8Zh5u",
    "type": "widget_highlight",
    "target": "#code-input",
    "content": "这里就是头插的三行代码：建节点、newNode->next = head、head = newNode"
  },
  {
    "id": "action_PiGcWSG9",
    "type": "speech",
    "text": "先单步执行第一条 newNode->next = head。此刻链表还是空的，head 的值是 NULL，所以 newNode->next 直接拿到 NULL。这就是空链表插入第一个节点的特殊情形：没有旧链可接，next 只能指向空。"
  },
  {
    "id": "action_JcdG9BzS",
    "type": "widget_highlight",
    "target": "#viz",
    "content": "每执行一行，这张链表图就同步刷新：head 箭头、newNode 箭头、next 连线"
  },
  {
    "id": "action_COyqktPb",
    "type": "speech",
    "text": "接着执行 head = newNode。注意，只有这一句执行完，head 才真正指向新节点；前一句只是把新节点挂到旧链上，head 本身没有动。你可以多点几次下一步，把 1、2、3 依次插进去，然后对比一下：插入顺序是 1、2、3，可从头往后读链表，顺序却是 3、2、1，最新插的永远在最前面。"
  },
  {
    "id": "action_M8OuAaWs",
    "type": "widget_annotation",
    "target": "#state-readout",
    "content": "这里的数值是实时状态，可以边执行边对照代码和图形"
  },
  {
    "id": "action_xdvlpoSG",
    "type": "widget_highlight",
    "target": "#reset-btn",
    "content": "随时重置，反复观察空链表插入第一个节点的过程"
  },
  {
    "id": "action_8owZwC3g",
    "type": "speech",
    "text": "把这三步在脑子里过顺了——先建节点，再接到旧链，最后才移动 head——下一页我们就把这段写成完整的程序，看看真实的 C 代码长什么样。"
  }
]
```

## 4. 完整程序（上）：节点结构与头插函数

Type: slide

Element: text_pDa-FFA5

```text
完整程序（上）：节点结构与头插函数
```

Element: text_PC4lH1c-

```text
#include <stdio.h>
#include <stdlib.h>
struct Node { int data; struct Node *next; }; /* ① 结构 */
 
struct Node* createNode(int value) { /* ② 建节点 */
    struct Node *n = malloc(sizeof(struct Node));
    if (n == NULL) return NULL;
    n->data = value;  n->next = NULL;
    return n;
}
 
void insertHead(struct Node **head, int value) { /* ③ 头插 */
    struct Node *n = createNode(value);
    n->next = *head;  /* ① 先接上 */
    *head = n;        /* ② 再改 head */
}
```

Element: text_4mBXD7_n

```text
① 节点结构 Node
data 存数据，next 指向下一节点
next = NULL 表示表尾
```

Element: text_JXlMxIW9

```text
② createNode(int value)
malloc 申请内存 → 赋 data
next 置 NULL，并检查 NULL
```

Element: text_Eol_dckC

```text
③ insertHead(**head, value)
n->next = *head;  *head = n;
二级指针改的是 main 的 head
```

### 授课动作

```json
[
  {
    "id": "action__KzQNdaz",
    "type": "speech",
    "text": "上一页我们把头插法拆成了三步动作：建节点、接旧链、移 head。这一页就把这三步真正写成 C 代码，先看整个程序的上半部分。"
  },
  {
    "id": "action_4L0_PbWb",
    "type": "spotlight",
    "elementId": "text_PC4lH1c-"
  },
  {
    "id": "action_ocbSpPip",
    "type": "speech",
    "text": "先看最上面两行：include 写 stdio.h 和 stdlib.h。stdio.h 是为了后面 printf 打印链表，stdlib.h 是给 malloc 和 free 用的。这里少一个，编译器就会警告，初学者最容易漏的就是 stdlib.h。"
  },
  {
    "id": "action_u5nf7SFr",
    "type": "spotlight",
    "elementId": "text_4mBXD7_n"
  },
  {
    "id": "action_AIEh7k3-",
    "type": "speech",
    "text": "接着是节点结构。struct Node 里面有两个成员：data 用来存数据，next 是指向同类型结构体的指针，指向下一个节点。注意 next 的类型是 struct Node *，结构体里引用自己，所以必须带 struct 关键字。当 next 等于 NULL 时，就表示这是表尾，后面没有节点了。"
  },
  {
    "id": "action_7aIDPwjS",
    "type": "spotlight",
    "elementId": "text_JXlMxIW9"
  },
  {
    "id": "action_8cdHmJyJ",
    "type": "speech",
    "text": "然后是 createNode 函数，对应我们说的第一步：建节点。它接收一个 int value，先用 malloc 申请一块 sizeof(struct Node) 大小的内存，然后把 value 赋给 data，再把 next 置成 NULL。特别强调一点：malloc 有可能失败，所以申请完一定要检查返回值是不是 NULL，如果是 NULL 就直接返回，不然后面访问就是野指针，程序会崩。"
  },
  {
    "id": "action_vUlQB4Oq",
    "type": "spotlight",
    "elementId": "text_Eol_dckC"
  },
  {
    "id": "action_2LCKkWA7",
    "type": "speech",
    "text": "最后是重点，insertHead 函数。它的第一个参数是 struct Node **head，是个二级指针。为什么要二级？因为我们要修改的是 main 函数里的那个 head 本身，而不是它指向的内容，C 语言里想改外面的指针，就得把指针的地址传进来。函数内部两步：先 newNode->next = *head，把新节点接到旧链上；再 *head = newNode，让 head 指向新节点。这个顺序千万不能反，反了老链表就找不回来了。"
  },
  {
    "id": "action_YsttfRty",
    "type": "speech",
    "text": "到这里，头文件、节点结构、createNode 和 insertHead 都写完了，这正好是头插法三步动作在代码里的完整落地。下一页我们补上遍历、释放和 main，让它真正跑起来。"
  }
]
```

## 5. 完整程序（下）：遍历、释放与 main

Type: slide

Element: text_px5OoLV4

```text
完整程序（下）：遍历、释放与 main
```

Element: text_xl2jWB1X

```text
void printList(Node *head) {
  Node *p = head;
  while (p != NULL) {
    printf("%d -> ", p->data);
    p = p->next;
  }
  printf("NULL\n");
}
```

Element: text_lQ4hkvgP

```text
void freeList(Node **head) {
  Node *p = *head, *next;
  while (p != NULL) {
    next = p->next;
    free(p);
    p = next;
  }
  *head = NULL;
}
```

Element: text_H9ykoDg9

```text
int main(void) {
  Node *head = NULL;
  head = insertHead(head, 1);
  head = insertHead(head, 2);
  head = insertHead(head, 3);
  printList(head);
  freeList(&head);
  return 0;
}
```

Element: text_v2NkcFfZ

```text
预期输出：3 -> 2 -> 1 -> NULL
```

Element: text_g3bgyB14

```text
提示：malloc 与 free 必须成对出现，用完即释放
```

### 授课动作

```json
[
  {
    "id": "action_6g2UWJgk",
    "type": "speech",
    "text": "上一页我们把节点结构、createNode 和 insertHead 都写好了，这一页把剩下的遍历、释放和 main 补齐，让这份代码真正能编译、能跑起来。"
  },
  {
    "id": "action_YmP9dlRh",
    "type": "spotlight",
    "elementId": "text_px5OoLV4"
  },
  {
    "id": "action_jq_Pimzh",
    "type": "speech",
    "text": "先看整体：这一页要补三个部分——打印链表的 printList、释放链表的 freeList，以及把它们串起来的 main。"
  },
  {
    "id": "action_erPU3eXU",
    "type": "spotlight",
    "elementId": "text_xl2jWB1X"
  },
  {
    "id": "action_kCmaZ4Gk",
    "type": "speech",
    "text": "第一个是 printList。思路很直接：先把 p 指向 head，然后用 while 循环判断 p 不等于 NULL。每进一次循环，先打印 p->data，再打印一个箭头“->”，最后 p = p->next 往后走一步。等 p 变成 NULL，循环结束，再单独打印一个 NULL，表示链表到头了。这样屏幕上就是完整的“数据 -> 数据 -> NULL”。"
  },
  {
    "id": "action_3Q2OWL6e",
    "type": "spotlight",
    "elementId": "text_lQ4hkvgP"
  },
  {
    "id": "action_E-H8tU0t",
    "type": "speech",
    "text": "第二个是 freeList。这里最容易出错，顺序一定要记牢：先保存 p->next 到临时变量，再 free(p)，最后让 p 走到刚才保存的 next 上。为什么必须先保存？因为 free(p) 之后，p 指向的那块内存已经还给系统了，再去读 p->next 就是访问已释放的内存，属于未定义行为。循环结束后，还要把 *head 置成 NULL，也就是 head = NULL，防止留下野指针（dangling pointer）。注意参数是 Node **head，这样才能真正改到调用者的 head 本身。"
  },
  {
    "id": "action_2AbudQnR",
    "type": "spotlight",
    "elementId": "text_H9ykoDg9"
  },
  {
    "id": "action_EB88r-vB",
    "type": "speech",
    "text": "第三个是 main，也就是整个流程的总指挥。第一步 head 初始化为 NULL，表示空链表；第二步依次用 insertHead 插入 1、2、3——还记得头插法的特点吗？每插一个都放在最前面，所以最终顺序是 3、2、1；第三步调用 printList 打印；第四步调用 freeList 释放所有节点；最后 return 0 结束程序。整份代码就这么闭环了。"
  },
  {
    "id": "action_RTWlfsIZ",
    "type": "spotlight",
    "elementId": "text_v2NkcFfZ"
  },
  {
    "id": "action_o6qTt_2W",
    "type": "speech",
    "text": "运行结果应该和我们推演的一致：3 -> 2 -> 1 -> NULL。如果打印出来是 1 -> 2 -> 3，说明你用的其实是尾插的思路，那就要回头检查 insertHead 里的指针改动顺序了。"
  },
  {
    "id": "action_6Ps_4gEp",
    "type": "spotlight",
    "elementId": "text_g3bgyB14"
  },
  {
    "id": "action_cBSs1QCm",
    "type": "speech",
    "text": "最后记住这条铁律：malloc 和 free 必须成对出现。每申请一块内存，就要检查它是不是 NULL；每用完一块内存，就要及时释放。养成“申请即检查、用完即释放”的习惯，后面写更复杂的链表、树，甚至做项目，都能少踩很多坑。下一页我们就一步一步追踪指针，把刚才这套代码真正“走”一遍。"
  }
]
```

## 6. 逐步追踪指针变化与预期输出

Type: slide

Element: text_PHpgjBDk

```text
逐步追踪指针变化与预期输出
```

Element: text_Hf7MjXx_

```text
① 初始
```

Element: text_CcpYflOT

```text
head
```

Element: text_s6WJjdIu

```text
NULL
```

Element: text_uH6DMUTr

```text
② 插入 1 后
```

Element: text_aY_VtA-4

```text
head
```

Element: text_OCFmeIcW

```text
1|NULL
```

Element: text_Oi6IB3-g

```text
③ 插入 2 后
```

Element: text_HEC5JIUe

```text
head
```

Element: text_nSDqJIcv

```text
2|·
```

Element: text_pRrg-Sfj

```text
1|NULL
```

Element: text_-DqxukRD

```text
④ 插入 3 后
```

Element: text_EBgdr49m

```text
head
```

Element: text_yV2pmfw1

```text
3|·
```

Element: text_9LX8a8Kj

```text
2|·
```

Element: text_ZFMIufM2

```text
1|NULL
```

Element: text__v0siplE

```text
预期输出
```

Element: text_3et1Gn2A

```text
3 → 2 → 1 → NULL
```

Element: text_zyJ99_3Q

```text
为什么顺序相反
```

Element: text_TGbaBP4F

```text
每次都在表头插入 → 后进先出（LIFO）：最后插入的最先被访问。
```

Element: text_GMSl7Emk

```text
常见错误
```

Element: text_vn_0jDvg

```text
× 忘记 head = newNode
```

Element: text_x7Uf6jan

```text
× 先改 head 再接 next
```

Element: text_8ONoidco

```text
× free 后仍访问 next
```

Element: text_RLqF34Hw

```text
× 忘记把 head 置回 NULL
```

### 授课动作

```json
[
  {
    "id": "action_GpDG6FRz",
    "type": "speech",
    "text": "上一页我们说了「申请即检查、用完即释放」，现在就把刚才那套头插代码真正“走”一遍——不跑程序，我们先用眼睛在纸上把指针一步步画出来。看这四个小图，就是同一段代码执行四次的快照。"
  },
  {
    "id": "action_7xZIlIsS",
    "type": "spotlight",
    "elementId": "text_Hf7MjXx_"
  },
  {
    "id": "action__gtCcgbl",
    "type": "speech",
    "text": "① 初始状态。这时候 head 里面装的是 NULL，意思是头指针没有指向任何节点，整个链表是空的。记住这一点很重要：空链表不是“head 不存在”，而是 head 存在、只不过它的值是 NULL。"
  },
  {
    "id": "action_OcyyZW-z",
    "type": "spotlight",
    "elementId": "text_uH6DMUTr"
  },
  {
    "id": "action_Uzp_rMpZ",
    "type": "speech",
    "text": "② 插入 1 之后。malloc 出来一个节点，数据域写 1，next 写成 NULL，因为它是目前唯一一个节点，后面没有别人。然后 head = newNode，head 就指过来了。现在 head 指向的这块内存，内容就是“1 加 NULL”。"
  },
  {
    "id": "action_eWjs83E4",
    "type": "spotlight",
    "elementId": "text_Oi6IB3-g"
  },
  {
    "id": "action_DehBybgz",
    "type": "speech",
    "text": "③ 插入 2 之后。新节点先是把自己的 next 指向原来的第一个节点，也就是 1 那个节点；然后 head 才改成指向 2。所以现在是 head 指向 2，2 的 next 指向 1，1 的 next 是 NULL。顺序一定要注意——先接 next，再动 head，这两步反了链表就断了。"
  },
  {
    "id": "action_VihW-IRw",
    "type": "spotlight",
    "elementId": "text_-DqxukRD"
  },
  {
    "id": "action_Jkhydcmr",
    "type": "speech",
    "text": "④ 插入 3 之后，同样的动作再来一次：3 的 next 指向 2，head 指向 3。现在整条链子就是 head → 3 → 2 → 1 → NULL。每一步都只改了两个地方——新节点的 next 和 head——其他节点一个都没动。"
  },
  {
    "id": "action_JV1UEDlM",
    "type": "spotlight",
    "elementId": "text_3et1Gn2A"
  },
  {
    "id": "action_Y_TqC4on",
    "type": "speech",
    "text": "那遍历输出会是什么呢？从 head 出发，打印 3，顺着 next 到 2，打印 2，再到 1，打印 1，最后遇到 NULL，循环结束。所以输出就是 3 → 2 → 1 → NULL。你在这里可以提前用纸笔预测一下，再跟实际运行结果核对，这个“预测—核对”的习惯特别能帮你抓出自己的思维漏洞。"
  },
  {
    "id": "action_-5EvLosA",
    "type": "spotlight",
    "elementId": "text_zyJ99_3Q"
  },
  {
    "id": "action_Qptpc-IE",
    "type": "speech",
    "text": "你有没有发现，我们明明是依次插入 1、2、3，输出却是 3、2、1？原因就一句话：每次都在表头插，最后插进去的自然站在队首，最先被访问。这就是后进先出，英文叫 LIFO（Last In First Out），和栈的行为一模一样。换句话说，用头插法建出来的链表，天然就是一个栈。"
  },
  {
    "id": "action_SLU8f-dC",
    "type": "spotlight",
    "elementId": "text_GMSl7Emk"
  },
  {
    "id": "action_yyF2W8Ru",
    "type": "speech",
    "text": "最后我们把几个最容易翻车的地方集中过一遍：忘记写 head = newNode，那新节点就挂不上，链表永远没变；先改 head 再接 next，原来的链子就找不回来了；free 掉一个节点之后还去访问它的 next，那是指向已经还给系统的内存，属于未定义行为；还有清空链表时忘了把 head 置回 NULL，下次再插就可能踩到野指针。这四条只要错一条，程序要么崩要么输出莫名其妙的数，回头调试时也优先从这四点上找。"
  }
]
```

## 7. 三道练习：检验你真的懂了吗

Type: quiz

```json
{
  "type": "quiz",
  "questions": [
    {
      "id": "q1",
      "type": "single",
      "question": "从一个空链表开始，依次用头插法插入结点 1、2、3，每次都把新结点插在链表头部。插入完成后，从 head 开始遍历并输出结点数据，输出顺序是什么？",
      "options": [
        {
          "value": "A",
          "label": "1 2 3"
        },
        {
          "value": "B",
          "label": "3 2 1"
        },
        {
          "value": "C",
          "label": "1 3 2"
        },
        {
          "value": "D",
          "label": "2 1 3"
        }
      ],
      "answer": [
        "B"
      ],
      "analysis": "头插法的特点是后插入的结点总在链表最前面。空链表插入 1 后为 1；再头插 2，得到 2 -> 1；再头插 3，得到 3 -> 2 -> 1。因此从头遍历输出顺序是 3 2 1。",
      "points": 10,
      "hasAnswer": true
    },
    {
      "id": "q2",
      "type": "multiple",
      "question": "下列用头插法把值为 value 的新结点插入到以 head 为头指针的单链表中的代码片段，哪些写法是正确的？（多选）",
      "options": [
        {
          "value": "A",
          "label": "struct Node *newNode = (struct Node *)malloc(sizeof(struct Node)); newNode->data = value; newNode->next = head; head = newNode;"
        },
        {
          "value": "B",
          "label": "struct Node *newNode = (struct Node *)malloc(sizeof(struct Node)); head = newNode; newNode->data = value; newNode->next = head;"
        },
        {
          "value": "C",
          "label": "struct Node *newNode = (struct Node *)malloc(sizeof(struct Node)); newNode->next = head; newNode->data = value; head = newNode;"
        },
        {
          "value": "D",
          "label": "struct Node *newNode = (struct Node *)malloc(sizeof(struct Node)); newNode->data = value; newNode->next = head; head = newNode; free(newNode);"
        }
      ],
      "answer": [
        "A",
        "C"
      ],
      "analysis": "A 和 C 都先把 newNode->next 指向原来的 head，再把 head 改为 newNode，所以新结点正确接到旧链表前面。B 先把 head 改成 newNode，再执行 newNode->next = head，会让 newNode->next 指向自己，并且丢失原来的链表。D 在把 newNode 接入链表后又 free(newNode)，head 会指向已经释放的内存，造成悬空指针。",
      "points": 15,
      "hasAnswer": true
    },
    {
      "id": "q3",
      "type": "short_answer",
      "question": "在头插法中，为什么必须先写 newNode->next = head，再写 head = newNode？请结合从空链表依次插入 1、2、3 的过程说明。",
      "commentPrompt": "评分细则：(1) 能指出 head 保存旧链表首结点地址，若先改 head 会丢失旧链表，占 40%；(2) 能说明 newNode->next = head 是把新结点接到旧链表前面，占 30%；(3) 能结合 1、2、3 的插入过程说明最终链表为 3 -> 2 -> 1，占 20%；(4) 表达清晰、术语准确，占 10%。",
      "analysis": "head 中保存的是当前链表第一个结点的地址。执行 newNode->next = head 时，新结点的 next 先记住旧链表头，这样新结点才能接到旧链表前面；然后再执行 head = newNode，让头指针指向新结点。如果顺序反过来，先执行 head = newNode，旧链表第一个结点的地址就被覆盖了，旧链表会丢失。结合例子：空链表插入 1 后 head 指向 1；插入 2 时先让 2->next 指向 1，再让 head 指向 2，得到 2 -> 1；插入 3 时先让 3->next 指向 2，再让 head 指向 3，最终得到 3 -> 2 -> 1。",
      "points": 20,
      "hasAnswer": false
    }
  ]
}
```

### 授课动作

```json
[
  {
    "id": "action_DH4JMlOM",
    "type": "speech",
    "text": "前面我们一步步追踪了头插法里指针的变化，也点出了容易出错的几个地方。现在用三道小题检验一下，还是围绕 1、2、3 这个例子。请每道题都自己先想清楚再作答，先不要急着看提示，我会在你提交之后陪你一起过一遍，看看哪一步卡住了。"
  }
]
```

## 8. 总结与延伸：头插法 vs 尾插法

Type: slide

Element: text_2isy2_QF

```text
总结与延伸：头插法 vs 尾插法
```

Element: text_Z6m4Ysu6

```text
① 建节点
```

Element: text_M9-sN61W

```text
② 接 next
```

Element: text_8zc6RV2h

```text
③ 移 head
```

Element: text_qEESn6g9

```text
头插法（head insertion）
```

Element: text_xpgtHJiB

```text
• 插入 O(1)，实现简单
• 结果：逆序链表
• 适合：频繁表头插入
```

Element: text_0h5tPdnN

```text
尾插法（tail insertion）
```

Element: text_S9YBix8J

```text
• 需维护尾指针 tail
• 结果：与插入顺序一致
• 适合：需保持顺序的场合
```

Element: text_q50zw4UF

```text
课后练习：把本课代码改成尾插法，比较两者的输出差异
```

### 授课动作

```json
[
  {
    "id": "action_W9-qW2J4",
    "type": "spotlight",
    "elementId": "text_2isy2_QF"
  },
  {
    "id": "action_OZySJWJd",
    "type": "speech",
    "text": "三道练习过完，我们这门课也走到最后一页了。最后这一页，我想把整节课的内容重新梳理一遍，把头插法和尾插法放在一起对比，帮你把这一块知识点彻底理顺，形成完整的结构。"
  },
  {
    "id": "action_4mApZZDd",
    "type": "laser",
    "elementId": "text_Z6m4Ysu6"
  },
  {
    "id": "action_GMoVGYnr",
    "type": "laser",
    "elementId": "text_M9-sN61W"
  },
  {
    "id": "action_cPYdIos9",
    "type": "laser",
    "elementId": "text_8zc6RV2h"
  },
  {
    "id": "action_Jr57ecGX",
    "type": "speech",
    "text": "先看左边这一排，就是我们的三要素记忆法：第一，建节点，用 malloc 申请一块新内存；第二，接 next，让新节点的 next 指向当前的 head；第三，移 head，把头指针（head pointer）挪到新节点上。就这三步，顺序不能乱，尤其是“接 next”一定要在“移 head”之前，否则原来的链表就找不回来了。"
  },
  {
    "id": "action_6gXtmxQl",
    "type": "spotlight",
    "elementId": "text_xpgtHJiB"
  },
  {
    "id": "action_kSrCTCAz",
    "type": "speech",
    "text": "回忆一下，这就是头插法（head insertion）。它的好处在哪儿？插入只需要 O(1) 的时间，代码短、实现简单，很适合频繁在表头插入的场景。但你要记住它的“副作用”：因为每次都插在最前面，最终得到的是逆序链表。这也是为什么我们依次插入 1、2、3，遍历出来却是 3、2、1。"
  },
  {
    "id": "action_kaqZQ51s",
    "type": "spotlight",
    "elementId": "text_S9YBix8J"
  },
  {
    "id": "action_rhAmXKiz",
    "type": "speech",
    "text": "那如果我们希望顺序和插入顺序一致呢？那就换成尾插法（tail insertion）。思路正好相反：每次把新节点挂到链表末尾，而不是插到头部。代价是需要额外维护一个尾指针 tail，每次插入时更新它，否则每次都要从头遍历到尾，效率就变成 O(n) 了。它的结果是链表顺序与插入顺序完全一致，适合需要保持顺序的场合。"
  },
  {
    "id": "action_eBDRMnpN",
    "type": "speech",
    "text": "所以怎么选？一句话——想要逆序结果、或者就是频繁在表头插入，用头插；想要保持顺序、按次序输出，用尾插。两种方法没有谁更好，只有谁更合适，关键看你的需求。"
  },
  {
    "id": "action_iW8DvKSd",
    "type": "spotlight",
    "elementId": "text_q50zw4UF"
  },
  {
    "id": "action_mHCQJ4V3",
    "type": "speech",
    "text": "最后留一个课后练习：把本课的代码改成尾插法，加一个 tail 指针，然后分别跑一遍，把两种写法的输出结果放在一起比较。你会发现，仅仅是插入位置的一个变化，输出的顺序就完全颠倒过来了——这个对比如果能亲手做出来，头插和尾插你就真的掌握了。"
  },
  {
    "id": "action_z5Iuj1C6",
    "type": "speech",
    "text": "这节课我们从结构体和指针出发，一步步走到链表的创建、遍历和释放，又用图示追踪了指针的变化，最后做了三道练习。链表这一块最吃的就是“指针指向哪里”的直觉，大家课后多画几遍图、多跑几次代码，慢慢就顺了。这节课就上到这里，同学们辛苦了，我们下次见！"
  }
]
```
