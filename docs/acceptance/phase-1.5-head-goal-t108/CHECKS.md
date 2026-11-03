# T108 零调用接线检查与交接

2026-11-03，执行者Lee。真实Provider0、真实模型规划/课程0；独立新课程评估未开始。T107独立评估原文原样引用，未改其结论。最终课程验收仍等待准确授权后真实执行。

## 已执行的必要检查

| 实际命令/环境 | 结果与证据 |
| --- | --- |
| `backend/.venv/bin/python scripts/run_head_course_goal_dev.py --prepare` | 已有测试容器edumind-phase1-t037-pg/127.0.0.1:15437；新专用T108库迁移到0050。没有生产库/Provider。 |
| `backend/.venv/bin/python scripts/run_head_course_goal_dev.py --test` | 新主链14 passed/0skip。含实际PG+ASGI的两示例、原目标/自述来源、规划记录/原引用、不改大纲、私有候选与程序答案、部分无解析/完整反馈、CSRF/跨用户/旧版本拒绝、来源/请求/父链篡改拒绝；真实入口MockTransport成功规划/教学及非法JSON/analysis阶段拒绝，原body解密一致、失败/STOP保留。 |
| `backend/.venv/bin/python -m pytest -q tests/test_free_course_planning.py`，cwd=backend，专用库edumind_catalog_p15_t008_t108_regression | 59 passed。原规划输入/可变场景/Schema/来源/原子持久化/围栏回归。保留既有数据库白名单，不放宽断言；最终以PYTHONPATH仅backend重验59通过，并独立确认普通app导入不加载头插/scripts依赖。 |
| `backend/.venv/bin/python -m pytest -q tests/test_head_course_replay.py`，cwd=backend，原专用T107库 | 18 passed。固定来源与旧typed反馈、原真实候选映射继续有效。未重跑旧浏览器或重开T106。 |
| `backend/.venv/bin/python scripts/run_head_course_goal_dev.py --check-migration` | 独立空迁移库head→0049→head；T108库已有新来源审计时降级拒绝。事务保留0050/原审计，未删除旧行。结果JSON见check-results。 |
| `backend/.venv/bin/python scripts/check_head_course_goal_browser.py`，专用开发环境 | 实际Chromium，API/PG全真，浏览器route mock0；A桌面1440、B手机390。现有目标输入提交原文，程序明确加载**离线规划/内容夹具**，既有页面自动进入v2；13帧说明/高亮、前后步/重置/播放/暂停；错误格式与四题正确反馈；刷新原scene_version/来源/完整反馈无重复POST，页面无横向溢出，pageerror0。不是模型教学质量证据。 |
| `pnpm --dir web exec vitest run tests/course-visualization.spec.ts tests/responsive-accessibility.spec.ts` | 15 passed。新增来源显式允许/缺来源拒绝/高亮/原文脚本转义回归；旧四种展示和响应/可访问性保持。 |
| `pnpm --dir web build`；变更TS/Vue的ESLint | vue-tsc/Vite构建、ESLint通过；新题干准确代码换行由pre-wrap保留，通用数组格式提示不再给具体数值。 |
| `backend/.venv/bin/mypy --follow-imports=silent` 六个相关后端源文件；变更Python的Ruff | 通过；实际命令见账本与交付清单。 |
| `backend/.venv/bin/python scripts/prepare_head_course_goal_package.py --check`；实际CLI `--inspect`；工作流/diff/冻结原件检查 | 准确摘要/Prompt/Schema/共享材料与实际构造一致；无发送。当前manifest及本地检查结果供审查，不自授执行。 |

所有PG命令只传专用测试环境，不从项目.env取值；运行环境在本机/tmp的0600文件，不进Git。例行权限只为访问测试Docker/本机网络，经实际工具放行。未执行无关全后端套件、全前端E2E、性能/负载测试或新Provider探测。

## 开发中发现与修正（不抹失败）

- 原操作deadline/config受不可变触发器保护，创建后修改期限被实际PG拒绝。已删除修改路径，保留原600秒，不放宽触发器，也不新建1800秒操作。首次故障见工具执行记录；本地未另保存该首次完整trace，不伪称存在日志。
- Mock授权夹具两次time.time造成“精确600秒”差值不等；改用整数时刻。Mock响应最初已预读，原collect拒绝iter_raw；改测试为ByteStream，真实原件规则不放宽。两失败trace保留/tmp/edumind-t108/pg-failed-window-fixture.txt及pg-failed-mock-stream.txt。
- 旧规划测试拒绝T108数据库前缀，按其既有白名单使用单独t008_t108_regression库后59通过；保留/tmp/edumind-t108/pg-failed-regression-database-guard.txt。首次复用脚本遗漏测试容器名，后显式选择15437容器；没有改断言或访问生产。
- 浏览器脚本最初等待手动“进入”按钮，但旧页面会自动进入已就绪课程；修正为等待实际来源区。新来源最初未加入旧展示组件允许条件，已明确限定origin后进入同一播放器，并添加组件回归。随后脚本使用错误aria标签“步骤演示”，改为实际“过程演示与代码对照”，失败记录在/tmp/edumind-t108/browser-failed-selector.txt。未改课程数据绕过断言。
- 兼容自查收窄新材料的导入：只有明确T108分支加载仓库实验模块，默认后端不依赖仓库根目录。普通模式标准导入检查已实际通过，记录normal-import.txt。
- 类型检查发现私有JSON/可空engine等边界，已加类型与实际守卫；离线来源说明改为明确“夹具未调用模型”，避免把夹具显示成模型成果。

/tmp是本机临时检查证据，不是独立保管原件，也不承诺永久存在。安全摘要/最终测试输出随本包提交，截图媒体不提交。真实批次将使用另建的长期私有目录，不复用/tmp的测试原件或假Key。

## 对原产品/实验契约的集中差异

1. 新目标限定一场景/两个新支持示例，复用原规划输出Schema，但加入准确服务器能力；旧通用规划不变。选例和大纲必须由真实模型产生，离线夹具只用于接线。
2. 新head-goal-course-v1教学Schema和四个迁移题键，程序答案/情境代替模型参考答案；不冒充旧B/C观察题协议、双臂或七角色准入。Schema引用/同源一致不证明教学正确。
3. 新来源审计＋generation_source；旧回放源仍严格固定。已有帧协议和同一组件明确接纳新来源；原replay字样类型名描述帧形状，页面不会标为既有回放。
4. 本机前台阶段桥接代替本批后台调度出站；不修改普通Scheduler预算。新操作budget=null/execution_mode明确分开，实际尝试/用量在本批vault，页面不会假报13次余额；窗口和原操作600秒均不可续。
5. 文本插值原文展示，参考答案原服务端私有；typed数组/整组反馈/暂定course_only/刷新重置帧保持。题干代码保留换行；不允许数值格式提示泄露答案。
6. 独立助手评估代替模型审核请求，并限制一次非事实措辞修复；不作正式人工签核。不降低T038门槛，不扩正式掌握度或动态生产开放。
7. 新一批C2/停止/原件保管风险需重新批准。入口仍受T102迟发反例影响，页面停止不杀终端HTTP，本机原件无独立抗回滚、金额无可验证硬上限。不能据此恢复T102。

准确批准对象为ADR0052 A—D及manifest；未获批准不登记真实窗口、不取得Key、不发真实请求。旧T104/T106/T107冻结包保持原字节；其历史manifest绑定的旧共享源文件应在对应历史提交核对，不要求后续实现文件永远不变化，也不把旧授权迁移到本包。

## 下一步与停止点

本任务目前只交付可审查接线和准确准备。真实授权后，以实际应用新输入课程登记新600秒窗口，真实规划→独立规划核验→模型完整首稿→独立核验/一次允许修复→原私有主链v2→实际浏览器完整检查→交独立教学评估。没有实际新课程则不能标T108 done。失败/unknown及时停止保存，不自动试错、扩主题、跑T038或修T102。
