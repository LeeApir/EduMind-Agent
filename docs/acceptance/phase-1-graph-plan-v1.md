# Phase 1 30节点清单与存储测量 v1

2026-10-09，ADR-0012的Proposed附件。只冻结课程元数据设计；没有发布课程或替换默认图。

## 精确清单

| ID | 节点 | 直接先修 | 来源编号 | 初始资格 |
|---|---|---|---|---|
| array | 数组 | 无 | ods-array | 原签核课程资格须复核 |
| c-pointer | C 指针 | 无 | gnu-pointers | 原签核课程资格须复核 |
| circular-queue | 循环队列 | array, queue | ods-array | 原签核课程资格须复核 |
| linked-list-concept | 链表概念 | c-pointer | ods-list | 原签核课程资格须复核 |
| linked-list-deletion | 链表删除 | c-pointer, linked-list-traversal | ods-list | 原签核课程资格须复核 |
| linked-list-insertion | 链表插入 | c-pointer, linked-list-traversal | ods-list | 原签核课程资格须复核 |
| linked-list-traversal | 链表遍历 | single-linked-list | ods-list | 原签核课程资格须复核 |
| queue | 队列 | array | ods-array | 原签核课程资格须复核 |
| single-linked-list | 单链表 | c-pointer, linked-list-concept | ods-list | 原签核课程资格须复核 |
| stack | 栈 | array | ods-array | 原签核课程资格须复核 |
| doubly-linked-list | 双向链表 | single-linked-list, linked-list-insertion, linked-list-deletion | ods-doubly | 仅元数据 |
| circular-linked-list | 循环链表 | single-linked-list, linked-list-traversal | ods-doubly | 仅元数据 |
| array-stack | 顺序栈 | array, stack | ods-array | 仅元数据 |
| linked-stack | 链栈 | stack, linked-list-insertion, linked-list-deletion | ods-list | 仅元数据 |
| tree-concept | 树的基本概念 | c-pointer | ods-tree | 仅元数据 |
| binary-tree | 二叉树 | tree-concept | ods-tree | 仅元数据 |
| binary-tree-traversal | 二叉树遍历（递归、迭代与层序） | binary-tree, stack, queue | ods-tree | 仅元数据 |
| binary-search-tree | 二叉搜索树 | binary-tree-traversal | ods-tree | 仅元数据 |
| balanced-binary-search-tree | 平衡二叉搜索树（红黑树概念） | binary-search-tree | ods-balance | 仅元数据 |
| binary-heap | 二叉堆 | binary-tree, array | ods-heap | 仅元数据 |
| bubble-sort | 冒泡排序 | array | opendsa-simple-sort | 仅元数据 |
| selection-sort | 选择排序 | array | opendsa-simple-sort | 仅元数据 |
| insertion-sort | 插入排序 | array | opendsa-simple-sort | 仅元数据 |
| quick-sort | 快速排序 | array | ods-sort | 仅元数据 |
| merge-sort | 归并排序 | array | ods-sort | 仅元数据 |
| heap-sort | 堆排序 | binary-heap | ods-sort, ods-heap | 仅元数据 |
| sorting-comparison | 排序算法对比 | bubble-sort, selection-sort, insertion-sort, quick-sort, merge-sort, heap-sort | ods-sort, opendsa-simple-sort | 仅元数据 |
| graph-representation | 图的表示（邻接矩阵与邻接表） | array, single-linked-list | ods-graph | 仅元数据 |
| breadth-first-search | 广度优先搜索 BFS | graph-representation, queue | ods-graph | 仅元数据 |
| depth-first-search | 深度优先搜索 DFS | graph-representation, stack | ods-graph | 仅元数据 |

共30节点/69有向边。完整三类关系、方向和来源映射见[plan.json](../../data/knowledge/expansion-v1/plan.json)。邻接矩阵/邻接表及递归/迭代不是额外图节点；其比较在各自节点内展开。

## 教材定位

- `gnu-pointers`：[GNU C Language Manual — Pointers](https://www.gnu.org/software/c-intro-and-ref/manual/html_node/Pointers.html)，Pointers / Pointer Declarations。2026-10-09核对状态：official search index; direct fetch timed out。
- `ods-array`：[Open Data Structures (C++), edition 0.1G](https://opendatastructures.org/ods-cpp/2_Array_Based_Lists.html)，Chapter 2, array-based stacks and queues。2026-10-09核对状态：official page fetched。
- `ods-list`：[Open Data Structures (C++), edition 0.1G](https://opendatastructures.org/ods-cpp/3_Linked_Lists.html)，Chapter 3, singly-linked lists and Stack/Queue interfaces。2026-10-09核对状态：official page fetched。
- `ods-doubly`：[Open Data Structures (C++), edition 0.1G](https://opendatastructures.org/ods-cpp/3_2_Doubly_Linked_List.html)，3.2, doubly-linked list and circular dummy sentinel。2026-10-09核对状态：official page fetched。
- `ods-tree`：[Open Data Structures (C++), edition 0.1G](https://opendatastructures.org/ods-cpp/6_Binary_Trees.html)，Chapter 6, rooted ordered binary trees; 6.1 traversal; 6.2 BST。2026-10-09核对状态：official page fetched。
- `ods-balance`：[Open Data Structures (C++), edition 0.1G](https://opendatastructures.org/ods-cpp/9_Red_Black_Trees.html)，Chapter 9, balanced search trees / red-black tree concepts。2026-10-09核对状态：official page fetched。
- `ods-heap`：[Open Data Structures (C++), edition 0.1G](https://opendatastructures.org/ods-cpp/10_Heaps.html)，Chapter 10, BinaryHeap。2026-10-09核对状态：official page fetched。
- `ods-sort`：[Open Data Structures (C++), edition 0.1G](https://opendatastructures.org/ods-cpp/11_Sorting_Algorithms.html)，Chapter 11 / 11.1, comparison sorting, merge/quick/heap。2026-10-09核对状态：official page fetched。
- `opendsa-simple-sort`：[OpenDSA Complete Catalog](https://opendsa.org/OpenDSA/Books/Catalog/html/genindex.html)，Insertion Sort / Bubble Sort / Selection Sort。2026-10-09核对状态：official index and SelectionSort indexed; some direct module requests unavailable。
- `ods-graph`：[Open Data Structures (C++), edition 0.1G](https://opendatastructures.org/ods-cpp/12_Graphs.html)，Chapter 12, matrix/list representations and graph traversal。2026-10-09核对状态：official page fetched。

引用只作为元数据编写依据，不转授正式资源资格。暂不可直读的模块细节在T031补充核验；不声称已读这些全文。来源不规定项目先修顺序。仅记录书名/章节/URL，没有复制教学正文。

## 查询与存储决策

复核当前Repository及catalog_package：图按进程只加载一次、确定性有序查询；catalog manifest要求匹配默认graph_version与全体ID。保留历史seed，独立扩展图及选择依赖，优先解决资格/版本隔离而非数据库迁移。

测量命令：`backend/.venv/bin/python data/knowledge/expansion-v1/check_plan.py`。每类500批次×30节点=15000查询，预热一遍；批次总时间除30，不是单请求P95。使用结构对象与现有get/prerequisite/successor方法；相似扫描和闭包为候选适配代码。没有PG、HTTP、并发网络或Neo4j测试，不作为发布SLA或不同数据库性能排名。

| 查询 | 每类调用数 | 中位摊销 ms | 批次摊销 P95 ms |
|---|---:|---:|---:|
| current | 15000 | 0.000036 | 0.000037 |
| prerequisites | 15000 | 0.000225 | 0.000251 |
| successors | 15000 | 0.003156 | 0.003454 |
| similar | 15000 | 0.000932 | 0.001001 |
| transitive_prerequisites | 15000 | 0.002140 | 0.002246 |

平台：Darwin/arm64，Python 3.11.16；Repository SHA256 `7b50ea44297e9f7de1de9cc2f82bd6640c15c8d9b6e3714a13eb85850fc48c06`；plan SHA256 `2bc0d0ff8769588734d17b26cb698c271b4e10356c704f5bd254e52b6d65d10f`。原始证据 `local-materials/phase-1-t030/measurement.json`，Provider请求0。

结论：当前30节点/69边的固定查询没有引入图数据库的需求或性能证据。推荐YAML/不可变Repository+PostgreSQL用户状态。T032仍需在实际版本化Repository上提交性能/版本切换/错误证据；当前结果不能冒充后续任务通过。

## 验证与后续

检查通过：唯一ID、全部教材映射、先修引用、无环、原10节点身份/先修和16关系保留、显式双向SIMILAR_TO、BFS队列/DFS栈传递依赖。稳定原图保持不变，原课程包及ADR-0011历史冻结字节不修改。

T030当前等待ADR批准，不计完成。批准后记录具体用户原话/摘要，完成T030独立提交；T031补齐有据可查的目标/误区/元数据并发布独立版本，T032实现Repository版本边界，T033完成缺课程的明确路径/UI行为。没有真实Provider、生产变更或新阶段启动。
