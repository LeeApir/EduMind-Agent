# T036 主要学习旅程实际浏览器验收

通过命令：`backend/.venv/bin/python scripts/check_p15_free_course_browser.py --run r04`。先核对专用PG标签/回环15437，在新库edumind_catalog_p15_t036_r04实际迁移至0048，启动独立Uvicorn8175与Vite5192、原数据库lifespan、实际Scheduler.work与TutorScheduler.work；真实Chromium经网络HTTP、cookie/CSRF、实际业务路由/SQL/SSE操作。浏览器API路由Mock数量0，既不注入静态原型也不替换接口响应。只有模型输出为确定性MockTransport/FakeTutor，默认真实网关构造禁止、socket/DNS仅允许回环；无.env或真实凭据，dynamic只在专用子进程有效，生产catalog_only保持。

1440桌面与320移动各完成：未提交目标→模型设置返回保留→提交目标→首场景可学且后续仍在生成→全部ready→准确题组作答及暂定比较→真实刷新按GET恢复且不重复写→明确同意后导师提问→选择准确反馈位置并提交待核对→影响/预算明确确认后局部修订→主动读取原子新版本→学习记录读取原v3作答→恢复准确v4阅读并刷新→真实图谱/无画像未知态/空签核目录→新课程注入末场景两次结构失败→已就绪场景仍可读并刷新恢复。每宽14张、共28张截图及逐请求method/path/status在/tmp/edumind-p15-t036-r04；均无页面横向溢出/JS异常，移动目录通过真实展开按钮核对。已视检320局部失败恢复及1440修订。

实际4次create、2次作答、2次反馈、2次导师、2次局部修订，刷新重复写0。Mock生成20次（含有意结构失败/修复），Mock导师2次，真实Provider0。此处的暂定作答不进入正式掌握度；旧作答显示原v3绑定和原参考比较，不拿v4答案重评。有效核定/撤销来源工程已由T035实际PG/HTTP独立覆盖，不冒充本项人工核定题组或真实教学质量。新库无签核目录/画像，诚实验证空态/未知，不伪造已有内容。

保留失败轮次：r01脚本未选择反馈位置，按钮保持disabled；补充准确位置选择。r02桌面全通过，移动试图读取折叠目录中的隐藏状态；改为按实际UI先展开目录，且将移动宽度从390收紧到320。r03两端28截图/旅程均完成，但最终汇总误把/src/api源码304算进业务API；改为仅路径以/api/开头，仍严格拒绝异常状态，仅允许首次/session401和无画像/profile/me404。r04全新库完整通过；无产品代码修改、无强制点击/隐藏门禁、未把失败轮次记pass。

`backend/.venv/bin/python -m pytest backend/tests/test_p15_browser_guard.py -q --junitxml=/tmp/edumind-p15-t036-guards.xml`实际9项通过（回环IPv4/IPv6/localhost允许；公网/私网/元数据IP和外域DNS拒绝；真实Gateway构造拒绝）。四个新增Python文件Ruff通过。`python3 scripts/check_p15_free_course_browser.py --check`严格离线核对原始文件SHA、28个准确截图名、API/副作用/模式与真实调用边界；不启动进程/SQL/请求，原件缺失不通过。新服务器/Vite均已停止，8175/5192无监听。

T035离线251项证据复核、41批准/50历史完整性及工作流/diff通过；用户原README与参考目录保持。截图/临时服务日志不提交Git，准确路径和SHA记录results.json。本项仅证明工程/界面旅程，不计真实Provider质量、性能或生产动态开放成绩。

用户最新要求完成当前T036后停止。完成提交后停止，不领取T037，剩余T037–T042保持todo；不push/merge/部署/真实探测，H封存及旧blocked不变。后续如恢复，从根task.json、本交接与完成提交继续。
