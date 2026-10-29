# 头插法试用代码复核材料

观察日期：2026-10-28；归档及复跑日期：2026-10-29。

## 来源和范围

评估助手通过用户指定的 DeepTutor 浏览器页面读取“单链表头插法 C11 入门示例”会话及 HTML 源码。既有检查将代码提取到临时目录，本次将仍存在的两份代码原样复制至此，不重新调用模型。

- [lesson.c](lesson.c)：聊天中完整教学程序的提取副本，保留程序内容，排版与原代码块不完全一致。
- [visual_code.c](visual_code.c)：复核用组合文件，将原程序的 `Node { int data; ... }` 定义与 HTML 展示的 `Node *push_front(Node **head, ...)` 函数组合。**它是明确构造的兼容性检查输入，不是 HTML 原件或模型独立返回的完整程序。**
- [verification.json](../../verification.json)：本次复跑命令、退出码、输出和文件摘要。

完整原始聊天导出、HTML 文件、Provider 请求响应和运行时配置未归档。这里足以复核已保存代码的编译与正常执行结论，不能重放完整生成流程或判断哪个内部模块承担审核责任。

## 复核命令

在仓库根目录执行，二进制写入临时目录：

```bash
cc -std=c11 -Wall -Wextra -Werror -pedantic \
  docs/reference/deeptutor/evidence/head-insertion-20261028/lesson.c \
  -o /tmp/deeptutor-reference-lesson
/tmp/deeptutor-reference-lesson

cc -std=c11 -Wall -Wextra -Werror -pedantic -fsyntax-only \
  docs/reference/deeptutor/evidence/head-insertion-20261028/visual_code.c
```

教学程序编译和运行退出 0，输出为：

```text
4 -> NULL
7 -> 4 -> NULL
9 -> 7 -> 4 -> NULL
```

可视化兼容性检查预期失败，实际编译退出 1：原 `Node` 没有 `value` 字段。这是被测样本的问题得到复现，不是所有检查都成功退出。

函数返回类型改成 `Node *` 且成功分支没有返回语句，是源码阅读发现的另一个接口问题；本次编译首先报告字段错误，不将未产生的后续编译诊断写入结果。没有把这个片段作为可运行程序执行。

## 可视化轨迹观察

当时读取的 HTML 源码包含以下状态映射：

```javascript
// 摘要转录：只保留用于核对的字段，不是完整 HTML 文件。
const states = [
  { values: [] },
  { values: [4] },
  { values: [7, 4] },
  { values: [9, 7, 4] }
];
const codeLineByStep = [null, 4, 5, 6];
```

显示代码第 4、5、6 行分别是赋值、连接旧 head、更新 head。状态却分别表示三次插入均已完成，因此图状态与高亮语句不构成逐语句执行轨迹。最终结点顺序正确，不代表中间映射正确。

当时点击产物卡片后，内置预览显示 HTML 源码。没有确认独立页面的按钮、键盘切换、动画效果或截图布局。不得把静态源码检查写成浏览器交互通过。

## 未覆盖内容

- malloc 失败注入、内存工具检查和其他输入规模。
- 三道练习的完整作答、判分和掌握度更新。
- 未初始化指针变体。
- 独立重复生成、相同模型和预算的对照。
- DeepTutor 全量测试套件及可视化专用插件的端到端流程。
