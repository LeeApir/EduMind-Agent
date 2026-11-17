# T034 响应式与可访问性整合

移动导航的焦点循环包含关闭按钮，背景与跳转链接在展开时inert，Escape恢复触发按钮，页面切换聚焦可见标题，屏幕变宽解除展开及背景隔离，卸载清理媒体监听。导航顶端与46px关闭栏对齐。课程长代码提供有名称的可聚焦局部滚动区；模型能力缓存前5项后的型号可继续展开，不额外读取或探测。沿用已批准视觉系统，不新增页面/API/能力。

实际执行：`pnpm --dir web exec vitest run tests/responsive-accessibility.spec.ts`新增6项通过；`pnpm --dir web exec vitest run`41文件298通过、0失败/跳过；`pnpm --dir web typecheck`、`pnpm --dir web build`通过；`pnpm --dir web lint`0错误、35条既有ProfileCard警告，相关文件定向eslint无警告。首次发现inert空字符串不满足Vue类型，改为true/undefined同时保证关闭时移除属性，重新类型/构建/全测试通过。未放宽断言。

浏览器命令：`backend/.venv/bin/python /Users/apir/.agents/skills/webapp-testing/scripts/with_server.py --server 'pnpm --dir web dev --host 127.0.0.1 --port 5191' --port 5191 -- backend/.venv/bin/python docs/design/phase-1.5-accessibility-t034/browser_check.py`。实际Chromium，业务HTTP明确合成Mock：1440/1024/850/620/390/320的学习首页、大纲、课堂、图谱、画像、记录、目录、设置8页共48截图，页面无溢出；可见表单原生标签/名称、真实Tab/Shift+Tab、关闭/切页/导师Escape焦点、背景不能获焦、宽屏恢复、未提交目标保留、代码ArrowRight滚动、减少动效及手动步进、图谱读取失败后只读恢复、目录空态均通过，0写请求/0页面异常。首次resize断言早于媒体事件，改为等待aria-expanded关闭后验证背景解除，完整重跑通过。截图/tmp/edumind-p15-t034，320课堂和1440图谱已视检；课程目录与导师均为布局内区域，不遮挡操作。

正文/弱化文字/强调/警告与对应背景对比度均≥4.5，焦点色对白底3.72，状态有文字/原生aria；不依赖颜色推断状态。结果及48截图SHA见results.json；截图是测试数据，不进入产品或Git。41批准及50历史原件、用户原README SHA、工作流/diff检查通过。

此项是界面验收，不冒充真实PG、模型教学质量、性能或全量辅助技术认证。Provider0、生产catalog_only、H封存不变。下一T035隔离PG/持久队列/HTTP与MockProvider集成，持续目标未完成。
