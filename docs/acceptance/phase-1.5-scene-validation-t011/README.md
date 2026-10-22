# T011：草稿确定性准入交接

新增版本化free-scene-hard-gate-v1及free_course_scene_validations只追加结果表，0038前向迁移。不调用Provider/语义Review，不读取旧reject/pass来决定新草稿准入，不赋予正式签核或评分资格。T010原始候选保持原文，清洗版本独立保存。

## 检查与清洗

check_scene先复用T010的严格结构/语言/数量/表达类型上限，再检查：块锚点非空且唯一；动作锚点在同一候选；show_step必须引用本候选可视化且索引在实际steps范围；其他动作step_index按schema为null；每一步元素ID唯一非空、next_id和highlight_ids只引用该步真实元素。不支持html/script/tool执行块或执行动作，额外身份/权限/版本字段按schema拒绝。

text.markdown及私有solution中的原始HTML/实体转义，显式Markdown链接、图片和引用定义的方括号变为字面文本，预先转义反斜杠防止已有转义取消防护。保留普通标题/强调。代码、题干、答案、可视化标签等是纯文本数据；代码和私有answer_key保留准确原文，不能按HTML渲染或执行。清洗不修改旧模型原始审计，也不改变答案来制造正确结论。

清洗结果是Markdown数据，**不是可信HTML**。将来前端Markdown渲染必须禁用raw HTML、自动链接及未批准插件；纯文本字段通过Vue插值/textContent显示，禁止直接v-html/innerHTML、HTML属性拼接或执行代码。本任务没有引入Markdown渲染器或前端入口，未声称完成浏览器XSS/E2E验收。内联/围栏中的方括号或反斜杠也可能显示转义标记；C代码教学应使用专用code块，以保持源码原样。首版不提供活动外链/远程媒体。

计算清洗后的content+actions+准确直接依赖整体规范JSON，超过64KiB拒绝CLEANED_SIZE_EXCEEDED，不截断正文或丢依赖凑限额。硬失败只返回版本化rule_id/固定码及cleaned=null，原始失败内容保留在T010私有审计。引用/大小/结构检查不判断教学事实、答案或用户目标兑现；普通语义意见不是硬门，不产生额外模型调用。

## 身份、持久化和边界

validate_candidate按owner/course/operation/result查询实际候选，锁序owner→course→operation。复核当前head基线、生成epoch/租约token/取消/PG时钟期限，重新加载真实请求、准确计划与必要上游，核对全部输入/调用/结果摘要。跨owner、错操作/候选、过期版本及继任epoch拒绝，不借新写权限采用旧候选；租约token不进入Prompt或准入输出。

同一候选+规则版本只保存一份accepted/rejected结果，原始摘要、清洗后摘要、规则版本和固定发现可追溯。重放重新检查实时绑定，不把旧accepted当永不过期发布凭证；返回深拷贝，改返回字典不会改历史。审计写入与最终SQL期限围栏在同一保存点，外层commit/rollback由调用者负责。失败原始生成只保存GENERATION_FAILED的拒绝事实，不被“清洗”为成功。通过结果仍含私有答案，不能作为公开响应序列化。

0038为T010候选增加同owner/course/id唯一约束以支持复合外键，并新增准入表/只追加触发器，旧0034–0037迁移原字节不改。带0037候选/场景/清单的隔离库实际前向升级，原始行摘要不变；存在准入事实时拒绝downgrade，不删除审计强退，用户删除沿既有级联。

本任务不写FreeCourseSceneVersion/head/ready事件/操作成功。T012负责受约束动作使用和静态呈现，T013负责可学习清单/事件的原子接线并再次复核实时来源；T017等负责确认缺陷后的可见性事实。未来正式发布及评分仍按各自契约，确定性accepted不等于语义正确、已签核或已核定答案。

## 实际验证

```sh
backend/.venv/bin/python docs/acceptance/phase-1.5-scene-validation-t011/run_checks.py --run-id r02 --output /tmp/edumind-p15-t011-r02
backend/.venv/bin/ruff check backend/app/services/free_scene_validation.py backend/app/models/free_scene_validation.py backend/app/models/free_scene_generation.py backend/app/models/__init__.py backend/alembic/versions/0038_free_scene_validation.py backend/tests/test_free_scene_validation.py backend/tests/test_free_course_migrations.py docs/acceptance/phase-1.5-scene-validation-t011/run_checks.py
(cd backend && .venv/bin/mypy app/services/free_scene_validation.py app/models/free_scene_validation.py app/models/free_scene_generation.py app/models/__init__.py)
python3 scripts/check_catalog_workflow.py
git diff --check
```

最终353项通过，0失败/错误/跳过：新准入40项、前置自由课程266项、旧图谱/路径47项。计数及证据摘要见results.json，过程见verification.txt。专用test-only PostgreSQL只绑定127.0.0.1:15437，使用18个新隔离库，不读.env或打印凭据。原始日志/XML在/tmp/edumind-p15-t011-r02；重跑须用新run-id/输出目录。

新测试覆盖恶意HTML/Markdown/实体/反斜杠与链接、结构/引用/清洗膨胀、合法内容、准确依赖、owner/操作/版本/epoch/取消/租约/事务回滚、幂等及只追加。带0037候选升级摘要、旧reject/pass/人工签核/评分完整摘要均实际核对；合法新草稿在旧reject存在时仍可接受，旧审核不被改写。HTMLParser只是清洗文本检查，不能计作实际浏览器渲染成绩。前置自由课程和旧路径/图谱回归均为离线/Mock/隔离PG，不是新业务E2E或真实质量/性能成绩。

30份批准规范/5份manifest及0034–0037历史迁移不变，Provider0/catalog_only/H封存/用户无关改动保持，无push/merge/部署。下一T012受约束授课动作与状态演示仍todo，未领取。
