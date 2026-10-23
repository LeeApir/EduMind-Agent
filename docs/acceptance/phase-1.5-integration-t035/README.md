# T035 新链零 Provider 集成验收

实际命令：`backend/.venv/bin/python scripts/check_p15_free_course_integration.py --run r02 --output /tmp/edumind-p15-t035-r02`。专用Docker标签phase1-dsl和127.0.0.1:15437核对后，18组各新建独立PG库，实际Alembic到0048、实际SQL/持久容量与派发/收据/事件，251项通过、0失败/错误/跳过。运行器不读取.env，去除Provider/凭据环境变量；dynamic仅在隔离API夹具中临时使用，生产catalog_only不变。MockProvider是原FakeAdapter/FakeTutor，不是远程请求或真实收费。

新增单一闭环test_p15_free_course_integration实际ASGI HTTP（FastAPI TestClient，无路由/数据库Mock）完成POST目标→PG排队→规划→首场景可读且后续未就绪→后续完成→可信本地合成题组准入→HTTP完整原作答→新客户端同owner恢复准确旧版本→SSE Last-Event-ID准确重放→HTTP影响确认与修订→暂存不替换head→原子替换后旧attempt原输入保留、比较反馈撤销→掌握度历史0.55到0、准确原来源及只重算一次，失效/跨owner均关闭。每个dispatch重建Scheduler及PG池，完全从持久状态恢复；5次合成调用，不借浏览器内存续跑。独立可信题组标签是测试夹具，不追认真实教学题组或公开人工权限。

故障/兼容组覆盖：scheduler39含租约过期、已发未知隔离、不自动重试、持久退避、package预算耗尽/共享、晚回调只结算；recovery29含取消和写入竞争、恢复读不写、新操作准确继承；revision10含原子暂存/失败保旧/事务回滚；feedback11、answers12、evidence15；API7含认证/CSRF/owner/SSE/旧版本；Tutor上下文10/共享调度11/API5；记录4/来源5；旧兼容12/Provider40/偏好26/catalog_only7/归档7。精确每组数量、库名和原始log/XML SHA见results.json。与T036真实浏览器+回环网络HTTP验收分开，不把本项TestClient说成浏览器或独立网络服务器。

r01原始证据保留/tmp/edumind-p15-t035-r01：前9组通过，导师scheduler组继承t043夹具，运行器误命名t044库导致11项setup错误；修正运行器为t043，为所有新库显式迁移（旧catalog模块没有迁移fixture），r02全量新库重跑通过。未改旧测试/产品代码、未删失败断言、未跳过。

`python3 scripts/check_p15_free_course_integration.py --check`只读准确结果/原始证据哈希、XML计数与case状态、固定组和库边界、41批准/50历史SHA及Provider0/catalog_only。绝不在--check隐式启动Docker、SQL或请求；原始/tmp证据缺失即拒绝，不冒充通过。`backend/.venv/bin/python -m pytest backend/tests/test_p15_integration_checker.py -q --junitxml=/tmp/edumind-p15-t035-r02/checker.xml`11正负例通过，覆盖缺失/篡改、错误/skip/非0exit、组或总数缺失、真实调用/模式越界，并禁止调用子进程。Ruff三文件、工作流、diff通过。此前T034前端298项及浏览器结果独立记录，不重复计入251。

H及50历史原件、41批准源/manifest保持；旧阶段blocked不追认。无真实Provider、部署、push/merge。本任务完成只证明上述工程闭环；下一T036实际隔离API/MockProvider主要浏览器旅程，质量和性能仍待独立真实授权与验收。
