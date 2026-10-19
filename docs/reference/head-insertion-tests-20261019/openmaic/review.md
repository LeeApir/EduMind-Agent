# OM 原样课程与独立检查

**课程已生成并原样保存；本次结果不满足“完整、可编译的 C 程序”和分配失败安全处理要求。没有让 OM 修改答案。**

## 原件

- 课程“单链表头插法微课”，ID `RE_zdH-6li`。8个教学场景（6张讲解/代码页、1个交互演示、1组3题），界面另自动显示完成页。
- [原始课程包](/Users/apir/Code/EduMind_Agent/docs/reference/openmaic/head-insertion-20261019/original-course.maic.zip)，401704字节，SHA-256 `fd34ca2ca08f73f1455e727cca822afafac75431b51796f6bece8ae57f11b808`。先保存并冻结摘要，再开始检查。
- `original-manifest.json`包含全部讲解/画布、交互HTML、题目、解析及授课动作；[可读版](/Users/apir/Code/EduMind_Agent/docs/reference/openmaic/head-insertion-20261019/independent-review/course-readable.md)便于查阅。
- 原生导出提示3个KaTeX CDN依赖未打包，ZIP只有manifest。课程内容完整保留，但不能声称所有离线依赖齐全。URLs见`external-dependencies.json`，原ZIP没有补写。

## 指定的三项检查

| 检查 | 结果与证据 |
| --- | --- |
| 分配失败路径 | **失败**。`createNode`失败返回NULL，`insertHead`直接访问`n->next`。第1/2/3次malloc失败注入均触发null-pointer诊断并异常终止。 |
| 调用者赋值 | **失败**。声明是`void insertHead(struct Node **head, int value)`，main却写`head = insertHead(head, 1)`等，参数级数及返回值用法均不符。后半段还使用了未定义别名`Node`。 |
| 资源释放 | **函数正常路径通过，整程序及失败路径不通过**。原始freeList先存next再free、最后清空head；独立函数测试分配3/释放3/live=0，再释放空表安全。但整程序不可编译，分配失败时也到不了释放调用。 |

定位：[NULL解引用](/Users/apir/Code/EduMind_Agent/docs/reference/openmaic/head-insertion-20261019/independent-review/original-program.c:14)、[函数声明](/Users/apir/Code/EduMind_Agent/docs/reference/openmaic/head-insertion-20261019/independent-review/original-program.c:12)、[main调用](/Users/apir/Code/EduMind_Agent/docs/reference/openmaic/head-insertion-20261019/independent-review/original-program.c:39)、[释放循环](/Users/apir/Code/EduMind_Agent/docs/reference/openmaic/head-insertion-20261019/independent-review/original-program.c:27)。

## 实际验证

按“完整程序（上）/（下）”展示顺序提取并拼接4个代码块；只去HTML排版、解码实体、保留段落换行和转换NBSP，未补typedef或修改C语句。来源映射在`independent-review/extraction-map.json`。

```text
clang -std=c11 -Wall -Wextra -Wpedantic -fsyntax-only docs/reference/openmaic/head-insertion-20261019/independent-review/original-program.c
```

退出码1，8个error、3个warning。见[编译日志](/Users/apir/Code/EduMind_Agent/docs/reference/openmaic/head-insertion-20261019/independent-review/original-compile.log)。**原样整程序没有运行，课程声称的预期输出不等于实际运行输出。**

另建`function-harness.c`独立测试原始函数体：测试环境提供缺失类型别名，按原声明以Node**调用，用宏跟踪malloc/free。这是测试驱动，绝不是修正后的课程程序，也不是原main通过。

函数测试使用`-Wall -Wextra -Wpedantic -Werror -fsanitize=address,undefined`编译，退出码0。

| malloc失败位置 | 退出码 | 观察 |
| --- | --- | --- |
| 不注入 | 0 | 输出`3 -> 2 -> 1 -> NULL`；allocated=3、released=3、live=0；再释放空表正常 |
| 第1次 | -6 | 注入时存活0节点，null-pointer诊断后异常终止 |
| 第2次 | -6 | 注入时存活1节点，null-pointer诊断后异常终止 |
| 第3次 | -6 | 注入时存活2节点，null-pointer诊断后异常终止 |

命令、退出码及日志索引见[test-results.json](/Users/apir/Code/EduMind_Agent/docs/reference/openmaic/head-insertion-20261019/independent-review/test-results.json)。分配/释放由测试驱动显式跟踪，未用LeakSanitizer证明泄漏；异常路径未到达释放，不推断未定义行为之后必然输出某个数值，也不把OS退出回收与程序显式释放混同。

## 内容一致性与三道练习

讲解、图示、步骤及练习统一使用从空表头插1、2、3，理论顺序3、2、1正确。主要一致性缺陷是前半段二级指针接口与后半段“返回新head”调用混用。

清单确有3题：单选、多选、简答。前两题有固定答案/解析；第三题`hasAnswer=false`，无固定answer字段，但有参考解析及评分细则。完成页只计2道客观题，不能据此说只有2题。多选A/C在malloc成功的前提下正确，但题面没声明该前提，选项也未处理分配失败，应记录这个安全前提缺失。

## 配置、过程与用量

| 项目 | 记录 |
| --- | --- |
| 模型/路由 | 界面及原生运行日志为`deepseek:deepseek-flash`；原配置Base URL为`https://api.deepseek.com/v1` |
| 思考模式/上限 | 前段真实请求未显式传thinking、reasoning_effort或max_tokens。官方当日约定默认思考开启、high、64K输出。没有套用旧deepseek-v4-flash目录的393216配置 |
| 原生段证据 | 依用户要求撤下所有代理、预算拦截和流式转换，以`pnpm dev --hostname 127.0.0.1`原命令启动，无临时环境覆盖。保留第1场景并继续其余场景，未改需求、大纲或OM源码 |
| 观察边界 | 原生段未抓取每次wire，不能称内部版本/全部参数被直接观测。配置由原文件/源码/日志核对，新增用量有reasoning tokens。版本映射来自官方文档，不冒充响应内部版本 |
| 可选能力 | 图像、视频、TTS、联网、深度交互关闭。深度交互不等于思考模式 |

来源：[官方模型/价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)、[请求参数](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/)，核对日期2026-10-19。

首次共享服务串入无关课程是执行者未先隔离的疏漏；两个代理中断段保留在`wire/`、`resume-wire/`，不作为原生性能/首次成功率证据。流式续传脚本只做离线模拟，没有真实请求。随后按用户指令恢复原生；最终原生日志未出现“间隔复习”课程生成。授权变更见`native-instructions.json`。

原生续生成新增16条用量行（9 content、7 actions，第二场景重复content也计入），与前段5条完整响应合计21条确认用量记录；另2条发送后用量未知。原生不抓包，不能把记录数冒充完整物理请求审计。

按当日高峰价及缓存用量，原生段参考1.27001032元，合计已知参考 **1.49849344元**；另2条未知不等于0，未查实际账单。旧预留不当作实际扣费；用户后续撤销预算保护，原生段没有按预算暂停。详见`native-usage-observed.json`与`native-summary.json`。

## 比较边界

这是新同类样本，含环境中断与恢复，只报告本次最终原件的问题。EduMind未运行这段新输入，不与旧的不同输入比较成功率，也不由单例推断OM或模型总体质量。后续对照应使用`submitted-input.txt`同一原文并分别冻结配置。
