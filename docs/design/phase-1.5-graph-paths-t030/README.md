# T030 图谱与路径

主导航接入独立GraphPaths页面，读取实际graph/mastery/catalog/path接口，提供可滚动先修关系图、键盘节点选择和等价列表。节点存在、签核课程可用性、可靠掌握度分别呈现；未读到证据或版本不符显示未知，不用0%补齐。图谱最多使用已有30节点结构，无新增课程/LLM范围。

可选当前自由课程按准确courseVersion读取清单关联和原始目标，不拿路径当前节点当实际教学关联；零关联明确展示。节点可带入学习页候选目标，确认后才替换输入，不自动生成或从先修知识改写目标。签核节点可打开真实目录。

owner域存视图/选择/图谱版本/目标和原路径请求。刷新仅GET原路径和准确历史结构，stale保留不自动重规划，旧结构读不到不回退，需明确选择当前结构。历史图不混入最新掌握度。创建/重规划仅显式操作，未知结果保留原键/原请求，身份变化拒绝补发；离开丢弃迟到结果。未知旧选择不自动替换。无新API、安全或持久化模型契约。

实际验证：`pnpm --dir web exec vitest run`37文件264通过、0失败/跳过，新增graph-paths8项；最终相关graph/shell16项再次通过。`pnpm --dir web typecheck`、`pnpm --dir web build`通过，`pnpm --dir web lint`0错误35既有ProfileCard警告，新增文件定向eslint无警告。工作流及diff通过。

浏览器：`backend/.venv/bin/python /Users/apir/.agents/skills/webapp-testing/scripts/with_server.py --server 'pnpm --dir web dev --host 127.0.0.1 --port 5187' --port 5187 -- backend/.venv/bin/python docs/design/phase-1.5-graph-paths-t030/browser_check.py`通过。真实Chromium，HTTP明确合成Mock并引用版本化30节点；六宽度无页面横向溢出、关系图/列表30节点、未知/签核可用性独立、原输入保留/候选确认、显式path/plan一次及刷新GET不补发。截图/tmp/edumind-p15-t030，1440/320已视检；图谱限高滚动避免长空白侧栏。不是新的PG或真实质量/性能证据。

Provider0、生产catalog_only、旧blocked/H不变，无push/merge/部署。下一T031画像与掌握度，阶段目标持续。
