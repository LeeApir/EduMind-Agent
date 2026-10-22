# T012：受约束动作与状态演示交接

新增free-scene-actions-v1、私有派生快照/静态诊断表free_course_scene_presentations及0039前向迁移。提供后端表示数据和纯状态切换器，不是前端播放器、代码执行器或已渲染媒体。

## 组件与准确绑定

prepare_presentation只接受owner/course/fence绑定的实际validation_id，并重新运行T011实时检查：原始候选/清洗摘要、owner、操作、head基线、计划/场景、生成epoch、取消/租约/期限均有效才可派生。返回绑定包含准确validation/result/plan/scene、expected_head及清洗摘要；expected_head是生成基线，不冒充未来发布后的course_version。单纯持有digest不授予发布或跨owner权限。

compile_presentation只从该清洗内容投影text/code/exercise/visualization块和highlight_block/show_step/pause时间线。数组/链表/栈/队列保留原始JSON步骤、文字替代及本步元素/指针/高亮引用，不执行模型代码。练习投影显式保留题干与short_text输入描述，去掉answer_key/solution；exercise_key仍是内部局部身份，不是T020/T022正式公开题组UUID，不能直接用作REST场景响应。

highlight_block可定位讲解或整个代码块，code_anchor仅指真实代码块。当前批准Action无line字段，因此不把可视化第n步猜成源码第n行，不增设未经设计的行范围语法；精确代码文本保持原样。show_step仅选取同一准确候选的实际帧。状态说明明确“状态步骤演示；代码仅作文本”，code_execution/media_requested/animation_executed保持false，不把图示当真实执行轨迹或正确性证明。

## 播放状态与降级

initial_state/transition是纯函数，仅支持play/pause、next_action、next_step/previous_step及固定故障信号。步骤在实际范围内钳位，到时间线末尾暂停；输入状态绑定准确presentation digest，错版本拒绝。无后台定时器、浏览进度/画像写入、Provider、编译器、网络、TTS或Manim调用；浏览器控件/计时器由后续课堂页面接线。状态返回深拷贝，不改原帧或已保存数据。

运行时未知动作、错误定位、越界步骤或损坏状态降级为已知正文的static/paused并返回ACTION_UNAVAILABLE，不能执行额外字段或携带任意错误原文。MEDIA_UNAVAILABLE/RENDERER_UNAVAILABLE信号保留静态正文与文字替代；不会把播放按钮当成已执行动画。源表示数据摘要损坏则拒绝PRESENTATION_CORRUPT，不能借静态模式显示未验证的新正文。

prepare_presentation可把调用方已知的固定故障原因保存为独立static快照（无时间线），同一validation+规则+故障原因幂等。此原因只是内部呈现故障记录，不宣称服务已探测真实媒体缓存或渲染结果；本任务没有媒体查找/下载/渲染入口。静态快照仍保留原始有效状态数据供文字对照。T011原始候选引用/结构硬失败继续拒绝，不能把ACTION_UNAVAILABLE用来跳过硬门；当前降级针对通过准入后的呈现故障或损坏播放状态。

## 持久化及后续接线

0039增加准入表同owner/course/id唯一约束，并新增复合外键绑定、只追加表示快照及固定诊断；不改0034–0038历史迁移。owner→course→operation锁下复核来源，再同保存点持久快照与SQL期限围栏；调用者负责外层commit/rollback。同键重放仍复核实时源绑定，旧epoch/head、取消或过期不因选择static而放行。有快照时拒绝downgrade，用户删除沿既有级联。

本任务不写场景正文版本、head、ready事件或操作成功；T013负责准确内容/清单/事件的原子接线，后续API和课堂组件负责公开投影及实际交互。Markdown仍须遵守T011的禁raw HTML/autolink/plugins及纯文本转义策略，不得将代码/标签/题干当HTML执行。本轮没有浏览器播放、渲染安全、真实教学质量或性能验收声明。

## 实际验证

```sh
backend/.venv/bin/python docs/acceptance/phase-1.5-scene-actions-t012/run_checks.py --run-id r01 --output /tmp/edumind-p15-t012-r01
backend/.venv/bin/ruff check backend/app/services/free_scene_actions.py backend/app/models/free_scene_actions.py backend/app/models/free_scene_validation.py backend/app/models/__init__.py backend/alembic/versions/0039_free_scene_actions.py backend/tests/test_free_scene_actions.py backend/tests/test_free_scene_validation.py backend/tests/test_free_course_migrations.py docs/acceptance/phase-1.5-scene-actions-t012/run_checks.py
(cd backend && .venv/bin/mypy app/services/free_scene_actions.py app/models/free_scene_actions.py app/models/free_scene_validation.py app/models/__init__.py)
python3 scripts/check_catalog_workflow.py
git diff --check
```

最终387项通过，0失败/错误/跳过：新动作34项、前置自由课程306项、旧图谱/路径47项。计数、源文件及原始日志/XML摘要见results.json；过程见verification.txt。既有test-only PostgreSQL绑定127.0.0.1:15437，使用19个新隔离库，不读.env/不打印凭据；原始日志/XML在/tmp/edumind-p15-t012-r01。重跑使用新run-id/输出目录。

新测试覆盖四种结构、准确动作/代码块、前后步界限/末尾暂停、私有答案剔除、固定故障静态降级、原数据/返回副本隔离、摘要损坏/错版本拒绝、实时owner/head/操作/epoch/取消/租约、事务回滚/幂等/只追加和有数据拒绝回退。T011旧行迁移摘要检查改为固定升级前的同一表集合，保留逐字节比较断言，避免将后续新增空表误算成旧行变化。前置准入/生成/图谱/路径及旧链回归均在离线/Mock/实际隔离PG中运行。

30份批准规范/5份manifest及0034–0038历史迁移保持原字节。Provider0/catalog_only/H封存及用户无关改动保持，无push/merge/部署。下一T013首场景与后续场景增量可见仍todo，未领取。
