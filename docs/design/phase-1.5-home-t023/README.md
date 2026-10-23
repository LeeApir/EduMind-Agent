# T023 目标首页交接

LearningHome 使用现有GET本人自由课程列表/签核目录，POST课程创建；无节点/画像问卷前置。代码语言可选，时长尚无批准的请求字段，因此不提供无效控件。课程类型/签核/生成版本与未知学习进度分别呈现；未放入原型记录。签核入口打开原目录，原动态学习仍保留独立入口。

创建请求绑定当前owner/CSRF/稳定幂等键，sessionStorage保存owner域内目标、同体请求与原回执，不存CSRF/凭据。失败/刷新重试同一操作，成功回执不重复POST；修改目标产生新请求。目录模式只提示不可用且保留目标。默认加载只读，不触发生成、旧课堂创建或设置修改。

实际：`pnpm --dir web exec vitest run tests/learning-home.spec.ts tests/workspace-shell.spec.ts` 13通过；`pnpm --dir web typecheck`/`build`通过；`lint`0错误35原有警告；工作流和diff通过。没有backend/API/迁移变更。

Chromium显式HTTP Mock：`backend/.venv/bin/python /Users/apir/.agents/skills/webapp-testing/scripts/with_server.py --server 'pnpm --dir web dev --host 127.0.0.1 --port 5180' --port 5180 -- backend/.venv/bin/python docs/design/phase-1.5-home-t023/browser_check.py`通过。4宽度1440/850/390/320无溢出，catalog_only零POST，网络失败刷新后保留目标与幂等键。截图/tmp/edumind-p15-t023，已视检1440；不当成PG/真实Provider或质量成绩。

T024替换请求保存后的状态承接区，实现准确大纲/进度/恢复；T025实现学习工作区。真实Provider0/生产catalog_only，无push/merge/部署。
