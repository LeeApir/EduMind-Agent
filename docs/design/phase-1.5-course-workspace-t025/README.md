# T025 渐进课程页与 T022–T025 批次交接

CourseWorkspace 接入准确课程清单、版本列表、场景投影与持久操作SSE。目录展示可读/等待/依赖/失败/失效，已就绪内容不因其他场景失败而隐藏。课程类型、签核身份、生成数量和本机查看记录分开；查看不作为正式掌握度或作答成绩。

同计划且既有ready绑定不变的普通追加自动更新，保留当前场景；修订/历史版本须显式选择，历史失效或阅读位置丢失均不自动替换。owner域sessionStorage保存版本/场景/滚动位置/查看记录/问题草稿；只在本机浏览器会话可用，不承诺跨设备。回首页刷新真实列表，继续学习恢复准确位置。离开/切课关闭SSE、取消GET等待，以独立epoch忽略迟到结果；前端离开不取消后台生成。读取/切页/刷新均不POST。

正文和代码用Vue文本节点渲染，Markdown当前以安全纯文本保留，不执行HTML/JS/C。受约束演示提供文字替代，题组可阅读/停用提示。导师区域可按需展开，问题可本机暂存和Escape关闭恢复焦点；明确发送未接入。完整演示控制/练习提交/导师发送/反馈修订分别留T026–T029，未假装已完成。

实际验证（2026-10-23）：

- `pnpm --dir web exec vitest run`：32文件 **227通过、0失败/跳过**，新增工作区7项；含局部失败/增量/修订围栏/历史失效/迟到结果/精确恢复/身份变化与撤回重读。
- `pnpm --dir web typecheck`、`pnpm --dir web build`：通过。
- `pnpm --dir web lint`：0错误；35条既有ProfileCard警告保留，无削弱规则。
- `python3 scripts/check_catalog_workflow.py`、`git diff --check`及准确批准文件/历史迁移归档SHA：通过，results.json记录35规范/manifest及50历史原件。
- `backend/.venv/bin/python /Users/apir/.agents/skills/webapp-testing/scripts/with_server.py --server 'pnpm --dir web dev --host 127.0.0.1 --port 5182' --port 5182 -- backend/.venv/bin/python docs/design/phase-1.5-course-workspace-t025/browser_check.py`：通过。

浏览器是真实Chromium，但业务HTTP/SSE使用明确合成Mock，无PG/真实模型；1440/1024/850/620/390/320无横向溢出，增量保持场景、选择后刷新准确恢复、导师草稿与Escape、历史失效通过，POST数0。截图在/tmp/edumind-p15-t025/course-*.png，results.json保留SHA，已视检1440/320。模型质量/性能/真实调度和PG组合不从这些结果推断；T021已有后端697检查未在本批重复运行。

批次：T022 a00c32b（其后91503ba补正空白与检查日志）、T023 a07daef、T024 2d6fbb1；T025完成提交以 `Task-Completed: PHASE-1.5-T025` 查询，避免写入自身哈希。原批准设计、后端/迁移/API契约不改，用户既有README/参考目录保留。真实Provider0、生产catalog_only、H及旧blocked不改，无push/merge/部署。

按用户要求完成T025后停止；T026–T042保持todo，下一T026待明确执行授权。
