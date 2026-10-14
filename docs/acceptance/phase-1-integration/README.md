# T038 跨模块集成验收

本轮仅本地隔离验证，真实 Provider 授权为 0。协议见 protocol.json，运行入口为 `backend/.venv/bin/python scripts/run_phase1_integration.py --run-id r01`。须在无 .env 的干净固定提交 clone 执行；复用已安装的锁定依赖，并逐项核对直接依赖版本与锁文件摘要。所有命令和实际结果保留在 ignored local-materials/phase-1-t038 下，完成后提交脱敏汇总。

后端逐文件新建独立测试库，防止撤销 DSL 政策影响后续文件；模型路径使用 MockTransport/合成 fixture。目录端到端使用原人工签核课程包、实际 PostgreSQL/Worker/Docker/Chromium；两个模板从空目录真实渲染，全部十节点学习/计分/重复提交/笔记/演示，最后重启 API 进程检查持久化并实际撤回版本。扩展图谱查询 30 节点与目录十节点并存。连接设置、原生选择、路由和扩展路径另以浏览器 Mock 契约验证。

唯一未运行的历史文件 test_catalog_signed_release.py 绑定旧缓存；其签核/导出/撤回行为由新目录浏览器流程覆盖，不计作该历史文件通过。真实厂商、真实 Ollama、Neo4j 均不在本轮，不能用 Mock 充当这些成绩。全部实际跳过项须列明，不默认为通过。

## 首次检查与修复

领取后 `backend/.venv/bin/mypy backend/app` 返回 3 错误：font_check.py:47 的 expr.value 类型、animation_dsl_compiler.py:156 的 len(object)、container_runner.py:12 的暂存目录 sibling import。用 AST Constant cast、pointers 列表 cast、TYPE_CHECKING 下的应用导入修复，容器实际仍用 sibling import。复查 166 源文件成功；Ruff 通过。该修复已加入 T038 scope，不改九动作/布局/安全限制。源码身份发生改变，T037 的人工签核与矩阵仍仅证明 15e52f1，不转授为本轮成绩。

验证脚本及修复先创建无 Task-Completed 标记的检查点，用于冻结干净源码；只有集成验证通过后的最终提交才完成 T038。已有开发服务和测试容器保留，不接触开发数据库。

严格配置复查：干净副本内从 backend 目录运行 mypy（加载 strict 配置）发现另外两处 Celery 无类型装饰器，改为显式注册，保持 Task 包装和信号订阅。此前根目录 mypy 的成功不代表 strict 通过。独立文件执行另暴露 classroom_persistence/learning_persistence 的 catalog_releases ORM 注册缺失；新 conftest 加载应用的实际注册，保留全部原断言，不改数据库 schema。

T038 同时执行阶段计划的定量接口：目录首屏 20 槽；扩展路径实际 PG/TestClient 100 操作（30规划/30读取/40历史重放），原始时序来自本轮 clone；独立复制 T036 已批准的 100 模板/100 SSE 语料，按本轮源码重新冻结，新数据库/缓存完整运行。SSE 分母 Job50/课堂50，包含 API 进程重启、终态、410→快照→重订阅。课堂只在 message_ready 已提交后断线，不宣称生成途中恢复。

首轮 r01（7c1001d）1758项后端中8失败/0错误/0跳过，另strict mypy/旧Mock浏览器/新增恢复检查失败，见 prior-r01.json。修复：统一应用ORM注册；ORIGINAL_SEND在fixture改写前导入；旧浏览器明确 dynamic runtime，模型设置补齐图谱/掌握度契约；恢复检查允许持久化练习页。所有原断言保留。旧导出夹具的伪MP4触发真实解码失败，改用固定禁网只读Manim镜像内PyAV生成内存黑帧，不作为教学动画质量证据；镜像无ffmpeg CLI的首个诊断失败亦保留本机日志。三组后端诊断共45项通过；核心Mock/连接路由图谱Mock及真实十节点目录+进程恢复诊断均通过，诊断不替代下一固定提交完整验收。

本地clone的 .git/info/exclude 仅登记 backend/.venv 与 web/node_modules 缓存链接；首次未登记时 clean gate 拒绝（未执行测试），未修改源码忽略规则。20条浏览器路径加载从实际 path/current fetch 开始计入网络，到节点DOM就绪+两帧；模块启动另外包含在首屏计时中。
