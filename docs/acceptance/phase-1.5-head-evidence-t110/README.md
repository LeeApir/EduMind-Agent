# T110：状态显示与教学证据缺口零调用修复

**本轮已修E01并提供S01/C01可引用依据，Provider调用0。T109 r01仍STOP/blocked，原教学文字与引用未修订，未发布新课程。** 实现及后续最小差异见[ADR0054](../../ADR/0054-head-course-evidence-supplement.md)。

## 实际API与页面

[开发应用](http://127.0.0.1:5198/)当前私有预览上下文已回到T109失败页。原course `6be90c82-adfd-408d-82b6-32125db0dcbf`、operation `ecb65468-da85-4772-8a5d-b7f1bb5e8fa1` 均保持，读取接口：`GET /api/free-courses/{course}/operations/{operation}`。

[实际失败操作与页面结果](actual-failed-page.json)：HTTP200，`execution_mode=finite_head_foreground`、`budget=null`、state仍failed/reason仍TEACHING_REVIEW_FAILED；页面状态“生成已停止”，无“剩余13次”、无“继续缺失内容”按钮，调整大纲禁用。course仍原v1/complete=false/scene_version_id=null，不是把失败改成成功或取消。截图`data/screenshots/t110-stopped-finite-page.png`为本机生成媒体，不提交。

[普通调度对照](actual-ordinary-budget.json)：明确标记的零调用状态夹具，使用原仓储存入当前身份的专用开发库，未调Provider/Worker；API未mock。其普通协议保留budget=0已用/13剩余，页面正常显示自身预算。夹具通过非凭据operation-ID的既有sessionStorage映射打开，未转移认证身份，不点击恢复表单。[夹具设置源码](ordinary-fixture.source.txt)可复核。这证明没有为隐藏前台错误预算而把所有课程budget清空；前端回归另以普通2已用/11剩余检查数值按返回结果显示。

主进程按已确认PID重启本机8178加载修复，5198前端热更新；原DB/会话保留，服务器原Provider工厂禁用和回环网络限制继续。本轮只读取T109状态，未重开其操作、deadline或授权。

## 两项教学声明如何对应证据

完整[版本化证据](teaching-evidence.json)和[原稿声明→事实映射](claim-evidence-map.json)由[程序生成器](../../../scripts/prepare_head_course_evidence.py)产生。

| 原稿声明/审核问题 | 可引用ID及来源 | 证明与范围 |
|---|---|---|
| S01 `failure_scope`称“只通过allocation_success条件掩码演示‘不分配’分支” | `head_evidence_v1.displayed_success_path`，来源为原13帧、对应trace状态及代码行 | f01/f07分配成功；f02/f08判空false；继续f03/f09写数据；f00–f12没有不分配帧，也没有真实malloc失败动画。审核者可以逐帧定位反驳，不需猜模型意图。 |
| C01 `paragraphs[5]`（从0计，第六个讲解段）论忽略两次返回值 | `head_evidence_v1.discard_return_comparison`，来源为同spec的单独discard_return计算、原basis.ignore_return及闭式核验 | caller在两次调用前后都为i0，最终从该入口只遍历[-8]，t0/t1不可达，分配失败0；事实正确，但不是主播放器13帧展示过的对照。原文仍列旧fact_ids，本轮不替它悄悄换引用。 |

新证据独立使用`head-teaching-evidence-v1`及自己的evidence_digest，带原materials/example/spec/basis/frames和引擎/模板来源。代码/事实/轨迹都是程序模型，没有C实际执行；两次判空是原有成功分配状态派生帧，不能误称原trace另执行了两次C条件。

[生成输入预览](generation-input.preview.json)将原payload和独立supplement组合；[正文请求预览](teaching-request.preview.json)使用实际构造器，明确展示/计算对照职责和可用ID。它们没有发送，也不是新模型候选。新ID只有显式带有效补充的输入才可引用，原输入不能借新ID通过。原完整教学Schema不变，程序验证ID和来源不冒充句子语义审核。

## 原稿、原件与旧材料仍可复现

T109原候选摘要仍`63323703659f109f164752680e95ca20870cda31dbe720f63aa32d7dcc05b3dd`；[原候选](../phase-1.5-head-reuse-live-r01/candidate.json)、原请求/响应/审核/STOP及整个r01交付目录字节不改。生成器从原HTTP正文按原请求/原payload重放得到完整相等record和candidate；旧m.body(payload)仍精确重建原请求，旧引用规则仍拒绝新supplement ID。

`claim-evidence-map.json`中的引用检查只在内存把该段引用设为新ID，验证新/旧输入接受边界；没有改原教学文字，没有生成/保存修订候选，没有借助手修改计模型成功。原S01/C01 stop评估不被追改。

原冻结manifest记录包含运行源码，因此本轮授权修源码后，在当前工作树直接跑旧CLI的冻结包check会报变更，这是正常门禁；不能重写旧manifest消除报错。原执行源码仍在`674fc06`，原结果记录于`dd8fb7b`。本轮用原响应/原请求/原payload重放，并按Git历史核冻结摘要，保证旧包保持可复核。

## 检查与交接

- `PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q backend/tests/test_head_course_teaching_evidence.py`：8 passed，实际两类事实、原稿重放、新ID显式准入与旧输入拒绝、帧/状态/basis/内容/来源/布尔类型篡改拒绝。
- 专用本机PG最小测试环境，`backend/tests/test_head_course_status_projection.py`：4 passed；两旧/新前台协议及普通/未知协议的真实API预算读取，Provider工厂禁止。
- `pnpm --dir web exec vitest run tests/head-course-status.spec.ts`：2 passed；前台failed显示停止、预算/恢复隐藏、读取不POST，普通2/11预算保留。
- `scripts/prepare_head_course_evidence.py --check`通过；三个变更业务源mypy、新Python Ruff、前端类型/构建/ESLint通过。只覆盖本轮变更，未重复通用调度/迁移全量回归。
- 实际浏览器原失败操作与普通夹具均按真实API读取；无新operation提交。普通夹具首次从首页打开无本机操作ID，因此显示只读状态，补齐既有非凭据ID映射后再读取；一次工具结果包装解析失败及切换后异步DOM过早断言如实保留于[browser-check-notes.json](browser-check-notes.json)，后者加等待“生成已停止”可见后原断言通过，没有删断言或改后端结果。

后续局部修订必须先准确允许`failure_scope`，并绑定此独立证据版本；C01只动审核指定段落的text/fact_ids，其他内容不动。详见ADR0054第3节，本轮没有调用预算、窗口、Key输入、教学替换或发布授权。T110完成后停止交回；T109/T102继续blocked。
