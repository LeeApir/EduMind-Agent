# 单链表头插法测试资料 · 2026-10-19

这里集中保存同一原文的 OM、EduMind 原失败、目标识别修复及完整复测资料。原始证据目录保留；本目录使用逐文件核验的副本，汇总不修改原始答案，也没有新增模型调用。

## 快速入口

| 资料 | 入口 |
| --- | --- |
| EduMind 最新完整课程候选（待人工复核、未发布） | [edumind-r02/course-candidate.md](edumind-r02/course-candidate.md) |
| EduMind 最新完整测试过程、模型配置和结果 | [edumind-r02/README.md](edumind-r02/README.md) |
| EduMind 三条代码路径的独立检查 | [edumind-r02/independent-review.md](edumind-r02/independent-review.md) |
| EduMind 原程序与实际编译/运行结果 | [candidate.c](edumind-r02/candidate.c)、[execution.json](edumind-r02/checks/execution.json) |
| EduMind 完整原生待审材料与8次调用记录 | [complete-review-case.json](edumind-r02/complete-review-case.json)、[run-summary.json](edumind-r02/run-summary.json) |
| 目标识别修复及零调用复测 | [goal-scope-r01/README.md](goal-scope-r01/README.md) |
| EduMind 首次生成前失败记录 | [edumind/README.md](edumind/README.md) |
| OM 最终独立检查、配置与过程 | [openmaic/review.md](openmaic/review.md) |
| OM 课程讲解、代码、练习与授课动作 | [openmaic/independent-review/course-readable.md](openmaic/independent-review/course-readable.md) |
| OM 原生完整课程包与下载演讲稿 | [课程ZIP](downloads/单链表头插法微课.maic.zip)、[演讲稿](downloads/单链表头插法微课-script.md) |
| OM 原程序及故障注入结果 | [original-program.c](openmaic/independent-review/original-program.c)、[test-results.json](openmaic/independent-review/test-results.json) |
| 所有运行共用的准确输入 | [submitted-input.txt](submitted-input.txt) |
| 副本来源、整理过程与文件摘要 | [collection-provenance.json](collection-provenance.json)、[collection-manifest.json](collection-manifest.json) |

## 目录

```text
head-insertion-tests-20261019/
├── README.md
├── submitted-input.txt
├── openmaic/                  # OM首次中断、恢复、最终原件、配置、截图和独立检查
├── edumind/                   # EduMind首次失败：未到达模型
├── goal-scope-r01/            # 3458e42目标识别修复及零调用复测
├── edumind-r02/               # 24dcfc2完整生成复测：课程候选、wire、审核、数据库和C检查
├── downloads/                 # 原生课程ZIP、manifest和演讲稿
├── auxiliary/
│   ├── health-pages/          # 当时的服务健康检查快照
│   ├── offline-mock-fixtures/ # 离线模拟，不计真实调用/费用
│   └── process-20261019-excerpt.txt
├── collection-provenance.json
└── collection-manifest.json
```

## 各阶段结果

| 阶段 | 结果 |
| --- | --- |
| OM 最终原件 | 课程已保存；整程序编译失败，分配失败路径出现NULL访问，调用接口不一致；释放函数正常路径仅在独立驱动中通过 |
| EduMind 首次 | GOAL_CLARIFICATION_REQUIRED；Provider0、未生成课程，代码检查未执行 |
| EduMind 目标修复 | 识别为linked-list-insertion；仅零调用解析验证，不代表完整生成通过 |
| EduMind 完整复测 | 8次真实DeepSeek调用，生成3场景完整候选，仍awaiting_human，0人工决定/0发布；三条内存路径检查通过，保留释放教学表述、c-pointer节点绑定及严格编译末尾换行问题 |

完整复测的思考模式为none，内容输出上限4096、计划/审核2048。OM分段传输与配置不同，不因为同名DeepSeek Flash就视为同配置；原有中断与缺失用量也不抹去。所有输入摘要一致：`ca258576f14b3298728b2ea18ce9c808d31314db7a453c64e6583a128afc6e2e`。单个样本不推断总体成功率，不混入旧的不同输入。

## 保存与追溯

新增和更新副本与其来源逐字节一致；OM课程ZIP、下载manifest等既有原件继续保持原摘要。原始文件夹不搬移，避免破坏历史签核、源码绑定和已有链接。部分子报告含当时的绝对路径及“尚未复测”描述，保留其历史语境，最新结果从本页进入。

本目录此前遗留的EduMind三个临时脚本副本已清理；OM临时代理也不恢复。必要的C故障注入源与实际结果保留。辅助模拟、旧环境中断、待人工状态均独立标注，不冒充正式课程或真实模型成绩。

原OM运行日志仍由活跃服务追加，本目录保留当时冻结的日志快照，不以稍后运行日志覆盖原测试证据。整理时只核验文件与引用，没有重启模型、重生成课程或代替人工签核。

`collection-manifest.json`覆盖当前本目录全部文件（自身除外）；各组内原有摘要文件用于原运行追溯。副本如需核对，以根清单及复制来源记录为准。

空白检查保留原始SSE分隔空行、课程提取稿和诊断日志中的空格，不为消除格式提示改写证据；其余新增整理内容检查通过。6份测试证据日志虽被通用日志忽略规则覆盖，仍按明确文件路径纳入完整归档。
