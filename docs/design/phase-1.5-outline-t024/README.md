# T024 大纲与生成进度交接

CourseOutline读取真实原目标、版本清单/场景状态与操作预算；GET EventSource统一协议，快照恢复原操作，不重发生成。首场景就绪默认进入只读场景；主动调整时（含刷新恢复）抑制自动导航。全课调整读取影响摘要，填写意图/确认后仅显式提交；运行中须主动停止并待可靠收尾。澄清只呈现服务端真实问题；结果/用量未知禁止继续发送。catalog_only允许读/停止，不创建新操作。

位置与操作按owner保存；显式操作使用owner/CSRF/幂等键，相同失败重试沿用原请求，刷新不发POST。SSE只读IDs/状态，正文从准确版本GET；切页/切课关闭连接、AbortController与epoch丢弃迟到结果。异常最多三轮只读重连，可手动重新读取。浏览器提前/过期游标不覆盖服务端快照。未关联图谱不作为失败。

基础CourseReading供本任务首场景阅读，T025扩展为完整目录/增量/版本工作区；练习交互、演示控制和导师发送留T026–T028，无虚假可用按钮。

实际命令：`pnpm --dir web exec vitest run` **31文件220通过0失败/跳过**（大纲6）；`pnpm --dir web typecheck`、`build`通过；`lint`0错误35原有警告；工作流/diff通过。旧设置输入回归改为先进入签核目录，仍断言保留输入及零Provider请求。初版Boolean可选prop被Vue默认为false，补显式true默认值；浏览器视检发现EventSource连接error不能作JSON业务error，补类型区分与回归，不减原断言。

Chromium：`backend/.venv/bin/python /Users/apir/.agents/skills/webapp-testing/scripts/with_server.py --server 'pnpm --dir web dev --host 127.0.0.1 --port 5181' --port 5181 -- backend/.venv/bin/python docs/design/phase-1.5-outline-t024/browser_check.py`通过。显式HTTP/SSE合成夹具；4宽度1440/850/390/320无溢出，编辑阻止跳转、主动停止/确认调整、首场景可读、刷新零重复POST通过，截图/tmp/edumind-p15-t024，已视检1440及320。非PG/真实生成/性能/质量验收。

Provider0、生产catalog_only、H封存/旧blocked不改；无后端/API契约/迁移变更，无push/merge/部署。下一T025；完成后停止。
