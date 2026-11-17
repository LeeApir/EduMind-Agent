# T026 代码对照与过程可视化

CoursePresentation消费公开SceneProjection的真实动作/状态，支持数组、链表、栈、队列。highlight_block定位准确代码/正文块，不发明未批准的行号；show_step只读当前表示的有效帧，pause明确暂停。播放/暂停、前后动作、前后状态、末尾停播、隐藏页/离开/新版本停播及减少动效均有界。

未知动作/额外字段、错误anchor/越界/损坏元素引用退为静态文字和原代码；不执行代码，不展示运行入口。批准API没有媒体Job状态字段，本任务不虚构媒体就绪/生成成功，不启动媒体请求，明确保留文字替代。前端读取要求actions数组，损坏DTO拒绝展示。

实际验证：`pnpm --dir web exec vitest run`235通过、0失败/跳过（演示8项）；typecheck/build通过，lint0错误35既有警告。`python3 scripts/check_catalog_workflow.py`、工作区/暂存diff检查通过。浏览器命令：

`backend/.venv/bin/python /Users/apir/.agents/skills/webapp-testing/scripts/with_server.py --server 'pnpm --dir web dev --host 127.0.0.1 --port 5183' --port 5183 -- backend/.venv/bin/python docs/design/phase-1.5-visualization-t026/browser_check.py`

真实Chromium、显式HTTP/SSE Mock；1440/1024/850/620/390/320无溢出，真实anchor高亮/状态步进/减少动效及既有准确位置恢复通过，POST0。截图/tmp/edumind-p15-t026已视检1440。四类结构/播放末尾/坏动作/坏引用/卸载计时器由单测覆盖。不是PG、真实模型质量或教学性能验收。

保持批准文档/后端API/迁移/旧签核不变，真实Provider0、生产catalog_only/H封存，无push/merge。用户已扩大为当前Phase 1.5持续执行，旧T025停止说明保留历史；本项独立提交后领取T027。
