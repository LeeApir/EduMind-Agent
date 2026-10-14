# T038 跨模块集成验收

本轮仅本地隔离验证，真实 Provider 授权为 0。协议见 protocol.json，运行入口为 `backend/.venv/bin/python scripts/run_phase1_integration.py --run-id r01`。须在无 .env 的干净固定提交 clone 执行；复用已安装的锁定依赖，并逐项核对直接依赖版本与锁文件摘要。所有命令和实际结果保留在 ignored local-materials/phase-1-t038 下，完成后提交脱敏汇总。

后端逐文件新建独立测试库，防止撤销 DSL 政策影响后续文件；模型路径使用 MockTransport/合成 fixture。目录端到端使用原人工签核课程包、实际 PostgreSQL/Worker/Docker/Chromium；两个模板从空目录真实渲染，全部十节点学习/计分/重复提交/笔记/演示，最后重启 API 进程检查持久化并实际撤回版本。扩展图谱查询 30 节点与目录十节点并存。连接设置、原生选择、路由和扩展路径另以浏览器 Mock 契约验证。

唯一未运行的历史文件 test_catalog_signed_release.py 绑定旧缓存；其签核/导出/撤回行为由新目录浏览器流程覆盖，不计作该历史文件通过。真实厂商、真实 Ollama、Neo4j 均不在本轮，不能用 Mock 充当这些成绩。全部实际跳过项须列明，不默认为通过。

## 首次检查与修复

领取后 `backend/.venv/bin/mypy backend/app` 返回 3 错误：font_check.py:47 的 expr.value 类型、animation_dsl_compiler.py:156 的 len(object)、container_runner.py:12 的暂存目录 sibling import。用 AST Constant cast、pointers 列表 cast、TYPE_CHECKING 下的应用导入修复，容器实际仍用 sibling import。复查 166 源文件成功；Ruff 通过。该修复已加入 T038 scope，不改九动作/布局/安全限制。源码身份发生改变，T037 的人工签核与矩阵仍仅证明 15e52f1，不转授为本轮成绩。

验证脚本及修复先创建无 Task-Completed 标记的检查点，用于冻结干净源码；只有集成验证通过后的最终提交才完成 T038。已有开发服务和测试容器保留，不接触开发数据库。
