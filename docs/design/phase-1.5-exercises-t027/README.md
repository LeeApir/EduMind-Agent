# T027 准确题组作答与证据状态

新增CourseExercise与courseExercises传输层，使用已批准的AttemptRequest/Receipt/GET协议；完整课程/场景/题组版本绑定。部分作答保留原文且不显示答案解释；完整作答展示暂定比较或可靠状态，course_only/admitted/revoked分别解释，不虚构掌握度增长。反馈每次重新GET，撤回/不可用/部分结果在客户端再关闭解释投影，原作答保留。

草稿按owner和准确绑定存sessionStorage；不把旧输入带入新版题组。同次提交持久保存请求/幂等键，重复点击受忙状态保护，未知结果锁定原请求；回执已知时恢复仅GET。历史作答引用按owner/course/逻辑题组保存，GET复核服务端回传版本再展示。历史版本、暂停、目录模式及身份变化阻止新提交，409保持旧绑定，不尝试最新答案。

实际：`pnpm --dir web exec vitest run` **34文件241通过、0失败/跳过**，练习新增6项；`pnpm --dir web typecheck`、`build`通过；`lint`0错误35原有警告；工作流、diff通过。前端既有后端协议未改，不将Mock当PG或真实质量证据。

浏览器：`backend/.venv/bin/python /Users/apir/.agents/skills/webapp-testing/scripts/with_server.py --server 'pnpm --dir web dev --host 127.0.0.1 --port 5184' --port 5184 -- backend/.venv/bin/python docs/design/phase-1.5-exercises-t027/browser_check.py`通过；真实Chromium/明确HTTP+SSE合成Mock，1440/1024/850/620/390/320无溢出、部分→完整两次显式提交/撤回解释/准确版本恢复通过。截图/tmp/edumind-p15-t027已视检320。Provider0、生产catalog_only、H及旧blocked保持，无push/merge。

下一T028当前场景导师；其后按用户持续Phase 1.5授权推进，不跨阶段。
