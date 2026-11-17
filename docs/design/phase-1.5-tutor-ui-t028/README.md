# T028 当前场景导师问答

CourseTutor接已完成T043–T045真实接口，绑定准确course/scene版本，显式确认“本次上下文涉及的练习将按辅助学习记录”；当前生成活动/历史版本/目录模式禁止新发送。一般解释不修改课程，正文修订另走影响确认。新提问使用owner域原请求/幂等键；未知结果保留原请求供明确确认，已知回执刷新只GET。未知发送/用量不开放新一轮，失败/超时不会自动重试。

复用持久SSE快照恢复并消费tutor_ready，正文由GET turn取得；当前轮次/本版本历史引用保存在sessionStorage，不保存Provider凭据。取消是明确操作，不会把关闭面板/离开页面等同于取消模型；关闭等待/请求并丢弃迟到结果。已失效状态再关闭正文投影，保留问题；不同版本不会借旧回复解释新课。回复/问题均Vue纯文本，未使用v-html。

实际：`pnpm --dir web exec vitest run` **35文件248通过、0失败/跳过**（导师7项）；`pnpm --dir web typecheck`、`build`通过，`lint`0错误35条既有ProfileCard警告；工作流/diff通过。T043–T045已单独实际PG/HTTP验证，本项前端不重复宣称新PG成绩。

浏览器：`backend/.venv/bin/python /Users/apir/.agents/skills/webapp-testing/scripts/with_server.py --server 'pnpm --dir web dev --host 127.0.0.1 --port 5185' --port 5185 -- backend/.venv/bin/python docs/design/phase-1.5-tutor-ui-t028/browser_check.py`通过。真实Chromium/明确HTTP+SSE合成Mock；六宽度1440/1024/850/620/390/320无横向溢出，辅助确认、持久ready事件、回复转义、刷新GET无补发、失效隐藏、主动取消/正文不变通过。截图/tmp/edumind-p15-t028，视检320；截屏前回到页面顶部，避免full-page将滚动中的fixed/sticky元素错误放进文档中段。不是模型真实质量/性能证明。

Provider0，生产catalog_only及H/旧blocked保持，无push/merge/部署。下一T029反馈与局部修订，当前Phase 1.5持续目标尚未完成。
