# T010：按大纲生成场景内容交接

新增私有free_scene_generation生成器、准确输入加载/审计服务、free_course_scene_generation_results模型及0037前向迁移。复用已批准ADR0025/0026中的混合场景、规模、私有答案、准确依赖和失败保留边界，不经过旧固定三资源/逐关Review链。

## 输入和单次生成

load_inputs限定owner/course/operation/plan/scene及expected_head，重验请求链和准确计划摘要、来源结构；输入摘要包含生成时lease_epoch，不包含租约token，旧候选不能借新epoch保存。计划必须绑定当前操作请求；沿场景依赖闭包读取准确清单中的必要上游正文/动作/依赖摘要，按计划顺序传入，最多7个。缺失必要正文报DEPENDENCY_UNAVAILABLE；无依赖的后续场景可独立准备，不假装已经完成调度。原始目标、所有请求来源、有据画像（未知保持未知）、共享示例/术语/约定和准确目标场景均进入真实Gateway请求。

版本化Prompt free-scene-generation-v1和schema free-scene-candidate-v1支持一个场景混合text/code/exercise/visualization，必有非空教学text，其余表达类型遵循计划。首版zh-CN和C/null，不支持的语言发送前拒绝；C代码只作文本，不编译或执行。单场景最多32块/100动作，可视化仅array/linked_list/stack/queue、最多50步/每步32元素，含文本替代，不启动Manim或媒体调用。

私有练习沿ADR0026：题组2–4道short_text题，题目有局部question_id、answer_key和solution，exercise_key仅为候选局部键；UUID和exercise_version_id由后续正式身份逻辑分配。类型/计数/必需字段与重复题目键检查不证明参考答案正确。公开投影必须去掉私有答案，并按T022/T020赋予准确身份；当前候选不是HTTP SceneProjection。

generate_once只调用一次Gateway，retry_safe=false，不自动重试/格式修复/语义改写或切换Provider。发送前必需authorize_send回调，拒绝或请求被回调修改则零发送。当前仅Mock回调，不具真实出站授权；T014/T015须提供持久attempt、token/费用预约、模型能力/上下文上限、租约续期与未知发送隔离。单调用max_output_tokens=8000/timeout<=120s；128000字节输入只是安全边界，不等于32000token或费用保证。超限拒绝而不截断原目标/依赖，实际计数需覆盖完整Prompt/schema。

## 结果、审计和准入边界

生成结果仅为candidate或failed。有效候选/有界无效响应保留私有原文；超过64KiB或不可规范序列化的响应不保存伪造替代文本，固定SCHEMA_INVALID仍保留。Provider拒绝、schema无效、超时/未知发送使用PROVIDER_REJECTED/SCHEMA_INVALID/OUTCOME_UNKNOWN，不存厂商异常文本。取消传播，不伪造成功或返还未知费用。

SceneOutcome记录本次Gateway发送尝试数1及其报告用量；未报告整体/部分用量保持null，不能填0。这是单次调用结果审计，不是完整持久发送账本：崩溃前预约、取消后在途计数、整操作13次/整课40次及累计token/费用必须由T014持久attempt实现，审计条数不能替代预算。真实Provider调用为0，Mock次数与实际调用分开。

persist_outcome不调用网络。owner→course→operation加锁后复核准确存储输入、输入/调用/正文/用量摘要、head及epoch/token/取消/PG时钟租约和截止时间。调用键按owner/course/operation/scene唯一；同键同结果只返原result_id，不调用模型，不更新正文；异结果拒绝。审计写入和SQL围栏在同一保存点，外层commit/rollback由调用者负责。只追加审计、用户删除沿已有级联；有审计时0037拒绝downgrade，不删历史强退。

本任务不创建新FreeCourseSceneVersion、不切head、不写ready/scene_ready/first_scene_ready或操作成功。失败也不把整个操作提前改为failed；T014负责步骤状态和独立后续步骤的实际调度。T011/T012负责完整清洗、锚点/动作/视觉引用和执行安全的确定性准入；T013才把通过硬门的准确候选接入可学习清单/事件。当前代码不会将尚未清洗的候选公开，不宣称场景或整课已可学。

## 实际验证

```sh
backend/.venv/bin/python docs/acceptance/phase-1.5-scene-generation-t010/run_checks.py --run-id r04 --output /tmp/edumind-p15-t010-r04
backend/.venv/bin/ruff check backend/app/agents/free_scene_generation.py backend/app/services/free_scene_generation.py backend/app/models/free_scene_generation.py backend/app/models/__init__.py backend/app/services/learning_stage_gateway.py backend/alembic/versions/0037_free_scene_generation.py backend/tests/test_free_scene_generation.py backend/tests/test_free_course_migrations.py docs/acceptance/phase-1.5-scene-generation-t010/run_checks.py
(cd backend && .venv/bin/mypy app/agents/free_scene_generation.py app/services/free_scene_generation.py app/models/free_scene_generation.py app/models/__init__.py app/services/learning_stage_gateway.py)
python3 scripts/check_catalog_workflow.py
git diff --check
```

最终313项通过，0失败/错误/跳过：新场景54项、前置自由课程212项、旧图谱/路径47项。原始日志/XML在/tmp/edumind-p15-t010-r04；计数、来源与摘要见results.json；过程及失败修复见verification.txt。Runner仅使用已有test-only PG容器127.0.0.1:15437和新的17个隔离数据库，不打印凭据、不读.env、不调用真实Provider。重跑使用新的run-id/输出目录。

测试覆盖1–8场景、混合表达、共享约定/原要求、实际必要上游正文、私有答案、语言/计数/大小边界、Provider失败/超时/取消、发送前拒绝/请求变更、用量未知、跨owner/伪造输入/候选被改、取消/过期/新epoch拒绝旧候选/CAS/回滚、持久幂等、审计不可变和有数据拒绝回退。前置规划/关联/迁移及旧图谱路径API回归不代表真实模型、教学质量或新业务E2E验收。

30份既有批准规范/5份manifest和0034–0036迁移原字节不变，仅前向新增0037。catalog_only、Provider0、H封存、旧失败和用户无关改动保持，无push/merge/部署。下一T011确定性准入检查仍todo，未领取。
