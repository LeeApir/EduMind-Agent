# T029 内容反馈与原子局部修订

反馈绑定准确课程/场景版本及公开段落或题组；题目ID写入描述前缀，不扩展已批准API。待核对、已确认、未确认、更正分开呈现，学生提交不触发生成或自行确认错误。服务端确认后重读内容，可用性下降时关闭旧正文与练习并修正目录状态，仍可读取反馈回执。

修订先GET影响范围，明确受影响场景、证据撤销及13次/600秒操作预算，仍受课程累计限制；需要重规划时转大纲。只有明确确认才POST，不自动取消现有生成。未知结果保留原请求和幂等键；已知回执刷新仅GET。修订排队、下游等待、失败/取消/超时保留可用旧内容，已确认错误仍暂停；完整替换就绪后用户明确读取最新版本，不混用新旧题目和作答。owner与准确版本隔离本地草稿/回执，所有文本使用Vue转义。

实际验证：`pnpm --dir web exec vitest run` 36文件256通过，0失败/跳过，新增修订8项；`pnpm --dir web typecheck`、`pnpm --dir web build`通过；`pnpm --dir web lint`0错误35条既有ProfileCard警告。课程页原草稿恢复测试改用准确导师输入框ID，断言保留。工作流、diff及35批准/50历史SHA检查通过，用户既有README未动。

浏览器命令：`backend/.venv/bin/python /Users/apir/.agents/skills/webapp-testing/scripts/with_server.py --server 'pnpm --dir web dev --host 127.0.0.1 --port 5186' --port 5186 -- backend/.venv/bin/python docs/design/phase-1.5-revision-t029/browser_check.py`。真实Chromium/明确合成HTTP和SSE：六宽度无横向溢出、准确题目反馈、待核对/确认后暂停、影响确认、只读刷新、下游等待、旧版本保留与主动读取最新通过。移动端目录默认折叠，失效状态仍在目录DOM中；截图/tmp/edumind-p15-t029，320已视检。测试脚本最初未适配刷新后表单展开及移动目录折叠，修正定位后通过，未削弱业务断言。该证据不算真实Provider质量/性能或新PG成绩。

Provider0、生产catalog_only、H封存和旧blocked保持，无push/merge/部署。当前阶段未完成，下一T030图谱与路径。
