# T038 跨模块集成验收

r03 已完成，固定源码 `1f46d5b8fac1ecb932380ff8fce0144dfb4987af` 的干净副本全组通过，原始证据审计通过。汇总见 [complete.json](results/complete.json)，原始命令/分组见 [integration-r03.json](results/integration-r03.json)，目录与恢复见 [catalog-r03.json](results/catalog-r03.json)，SSE/模板见 [sse-template-r03.json](results/sse-template-r03.json)。

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

r02（4e599a8）后端1758/1758、前端189/189、全部类型/lint/build/Mock浏览器通过；实际100模板与100 SSE均通过、无出站、源码干净，但目录整体失败，见 prior-r02.json/prior-r02-catalog.json。20首屏及路径画面门槛通过；第二动画的计时变量在等待播放时变为undefined，Worker任务已完成。本轮没有采集导航/控制台细节，不能断言重载的唯一根因。依赖目录链接指向共享node_modules，开发优化缓存/HMR是待排查可能性；新轮改用同次构建产物的 vite preview（已核对固定Vite6.1.0源码proxy继承配置），隔离开发热重载，并断言动画过程只发生一次有意导航，完整失败轮次保留。不是把旧r02计时补成通过。

额外逐项比较20已签核样本：4e599a8编译出的Scene源码及SRT SHA均与15e52f1签核材料一致，见 compiled-byte-comparison.json；仅证明输出字节不变，旧性能与候选源码身份不转授。

## 最终结果与交接

后端118文件1758通过、0失败/错误/跳过；前端26文件189通过；严格mypy166源、Ruff、TypeScript、ESLint、生产构建及两组Mock浏览器全部通过。Python缓存离线冻结同步核对59包无变更，pnpm安装锁与仓库锁字节一致。

真实人工签核目录10节点/30资源/30题、2模板MP4/SRT导出、身份/CSRF/目录动态关闭、实际不同PID恢复与撤回全部通过。固定20首屏HTTP累计保守P95=0.123391s、DOM可读P95=0.923257s；20路径画面从fetch开始到两帧呈现最大108.600ms≤500。实际PG/TestClient的100路径操作P95/P99各组均≤200ms（分层原始时序在结果内）。

模板100/100，20独立未命中P95=9.283898s≤90；SSE100/100，Job50/课堂50，含重启/终态/过期游标快照重订阅。课堂Mock且仅提交后断线，全部真实Provider0/非回环出站0。完整r03无意外导航，两个动画探针各只有1次预期打开导航。

证据审计拒绝真实失败r01，并对r03的源码/协议/196+冻结路径、118XML计数、固定分母/门槛、签核/恢复/撤回及出站记录通过。r01/r02失败保留；旧DSL人工/性能仍绑定原提交，20编译源码/SRT一致证明另列，不补旧轮成绩。生成媒体、私钥及原始日志不提交，complete.json只保存可复查摘要。

无本任务遗留，不push/merge/发布、不开放动态能力。下一项T039需按ADR-0011另行指定真实目标/模型与请求、费用预算；已有“全部批准”仅批准设计/标签、实际预算仍0。
