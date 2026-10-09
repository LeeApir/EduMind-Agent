# T037 DSL安全与动作验收断点

T037未完成，状态blocked。真实Provider请求0，动态能力仍未开放。本次准备固定协议、可信样本、真实PG/Celery/Manim/HTTP/Chromium验收脚本；现有自动检查不代替实际媒体或人工核对。

源码基线79c7e20，safety-protocol.json/matrix-protocol.json绑定当前源码、锁文件、DSL规则、编译器、模板和原签核目录。20可信DSL用例覆盖全部九动作、数值-99/99/0、相等/大小比较；每个11动作、30.8秒。独立预期最终状态：n0/n1仅交换值、连接清除、指针NULL、访问标记n1、固定规模时间/空间O(1)。验证脚本按公开动作契约检查轨迹与字幕；这些是测试输入，非新课程签核。

固定矩阵：100合法DSL槽（20未命中+80命中）；100模板槽各模板50（20未命中+80命中）；另100缓存槽，DSL50/模板50分别报告P95且逐槽≤2秒，关闭浏览器缓存。全部真实媒体矩阵尚未运行。DSL候选通过真实准备/审核绑定/交接服务，审核仅使用明确MockGateway，无真实生成/审核质量主张；渲染/PG/队列/导出仍要求产品实现及实际容器。不得在实际运行前声称脚本通过。

已运行：

- `backend/.venv/bin/python scripts/run_phase1_dsl_safety.py --run-id r01`：285测试，262通过/23失败/0跳过。首次把所有文件放一个数据库，策略撤销测试按设计永久撤销策略，污染后续文件；旧迁移拒绝测试要求T025专用数据库前缀。原log/XML/source协议保留local-materials/phase-1-t037/safety-r01，计数见results/first-safety-failure.json。
- 修复执行隔离：每文件独立全新数据库，旧迁移测试使用明确t025_t037测试命名空间；不删除撤销记录，不削弱或排除测试断言。增加初始化子进程组20秒总超时，凭据只在捕获内存/测试子进程环境，不写日志。`--run-id r02`在初始化超时，0组/0测试执行，见results/second-initialization-failure.json；未验证修复有效，不计通过。
- `backend/.venv/bin/python scripts/verify_phase1_dsl_matrix.py`：离线20用例/schema/编译AST/轨迹/字幕/九动作与100/100/100分母通过，见results/offline-plan.json。初次比较oracle用词greater/less/equal与契约gt/lt/eq不符，改正确枚举后完整重跑；未削弱关系判定。
- 新增4个Python文件Ruff/格式检查通过。实际Docker最后10秒探测超时，results/runtime-readiness.json。通过open启动现有OrbStack后曾短暂恢复r01执行；此后容器接口再次持续超时。CUA明确报告Mac锁屏，已请求用户手动解锁。不能据此推断所有测试失败源于锁屏。

记录纠正：初始化观察期间曾写“未进入测试”，执行器后续恢复并完成r01，实际XML为285/23失败；明确更正保留results/first-run-observation-correction.json，不把误观察当最终证据。r02确实未进入测试。

恢复步骤：手动解锁Mac并确认OrbStack运行；有界检查Docker/专用PG/Redis，使用新的r03运行全部安全文件，不复用旧撤销DB。完整安全组通过后执行`backend/.venv/bin/python scripts/run_phase1_dsl_matrix.py --run-id r01`，不与其他渲染并发计时。若需修改源码/规则，另冻结新一轮，保留失败；所有样本失败/未运行均分别报告。矩阵完成后才生成与真实MP4/SRT/DSL摘要绑定的逐动作人工核对材料，核对通过前不done。当前未提供媒体材料，也未请求提前批准媒体。

测试媒体/证书/完整log放ignored local-materials，不提交生成媒体或凭据。当前只提交准备成果和blocked状态，不包含Task-Completed标记；T036已完成提交保持有效。无push/merge/部署/真实Provider预算使用。
