# T022 页面框架交接

复用批准视觉 token，增加 WorkspaceShell / WorkspaceState；旧课程目录、dynamic 原学习入口、连接设置与档位设置仍可到达。设置页仅首次打开时加载，学习区通过 v-show 保留输入。未实现的新图谱/画像/记录页面待相应任务，不提供空壳可用入口。

实际执行：`pnpm --dir web exec vitest run tests/workspace-shell.spec.ts` 8通过；`pnpm --dir web typecheck`、`pnpm --dir web build`通过；`pnpm --dir web lint`零错误/35条原有警告（ProfileCard/既有测试），不修改无关文件。`git diff --check`及五批准登记原件SHA检查通过。

浏览器：`backend/.venv/bin/python /Users/apir/.agents/skills/webapp-testing/scripts/with_server.py --server 'pnpm --dir web dev --host 127.0.0.1 --port 5179' --port 5179 -- backend/.venv/bin/python docs/design/phase-1.5-workspace-t022/browser_check.py`。真实Chromium/显式HTTP Mock，1440/850/390/320无溢出、移动菜单Escape返回触发键通过；截图 `/tmp/edumind-p15-t022/shell-*.png`，已人工视检320截图。目录未就绪及推荐读取错误如实呈现，没有假数据。首次夹具URL通配误拦源码，改为仅根/api/匹配；不是产品问题，修正后复验通过。

Provider0，生产catalog_only，无API/数据/迁移变化。下一T023接入目标首页；不提前实现T026以后行为。
