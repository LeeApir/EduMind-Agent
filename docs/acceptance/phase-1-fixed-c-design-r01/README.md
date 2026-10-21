# T065：固定 C 样本离线验收提案 r01

**零 Provider、零样本编译、零样本执行；待具体设计批准。**

需批准 [ADR-0019 A–D](../../ADR/0019-fixed-c-offline-verification.md)及 [manifest](manifest.json)列出的准确附件。不是再次申请 T056–T070 批次开发权限：根 T065 验收第5条要求“形成独立安全/数据契约批准入口后才实施T066–T069”，规划 §3 也要求具体隔离/限额先批准。

| 审阅点 | 具体选择 |
| --- | --- |
| 样本 | 仅已跟踪集合里的 EduMind r02 / OM 原样头插法；11份原件/来源/历史驱动摘要已绑定 |
| 驱动与真值 | T066提取映射、独立规格与逐文件维护者审阅登记后才准入；不修原件，不以模型输出作真值 |
| 工具链 | 独立Linux arm64/Clang19.1.7层，公开固定基础摘要+官方签名快照包；最终依赖/image/controller锁在运行前建立 |
| 隔离 | 一次性Docker，编译和运行均禁网、UID10001、只读根/最小包、无凭据/项目/socket挂载、默认seccomp、cap全去除 |
| 限额 | 1CPU/512MiB/64PID；编译30秒、运行5秒，输出每流64KiB；每轮64编译/40子进程/20分钟，无重试 |
| 结果 | 严格/普通、原main/接口驱动、数值/格式、Sanitizer/显式追踪分别记录；坏程序被正确检出仍是程序fail |
| 边界 | 本例路径证据，不写模型pass、不补人工签核、不发布、不改掌握度，不启动T040真实验收 |

[执行契约](execution-contract.md)冻结命令形态、预检、限额、清理和结果字段。[cases.json](cases.json)冻结来源摘要、6类矩阵、3个派生反例和6项隔离探针。[环境准备记录](environment-preparation.json)区分只读检查与未执行部分：读了一个从未启动容器的包清单后已删除，缺少Clang，尚不能声称可执行。

批准范围包含按指定官方来源准备工具链/离线构建及T066–T069固定域实施；源版本/平台/限额不可静默替换。包或环境不可用则停止，不降级宿主运行。真实Provider调用、Token及模型费用均0。生产catalog_only、旧失败和T040阻塞保持。

零调用核验：

```text
python3 docs/acceptance/phase-1-fixed-c-design-r01/check_proposal.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

上述只核验文档/摘要/任务契约，不编译或运行C，不证明容器隔离已实际生效。具体批准后另存独立登记，原Proposed提案及manifest保留原字节；T066的实际工具链与审阅准入新建运行锁，不原地更新本设计manifest。
