# T061 生成练习答案契约交接

依据[ADR0038批准登记](../../ADR/0038-approval-20261027.json) B，场景生成请求升级为free-scene-generation-v3。题干必须写明初始状态/准确执行位置和既有修改、有限答案域、规范输入格式；要求唯一可核对数字、显式列表中的标识符或固定选项标记。解释仍在讲解和solution中，不能把任意解释句当唯一精确键。选项/确定性追踪仍须覆盖原目标与难度，不能靠简单化题目过关。

完整request payload增加exercise_answers和按当前scene.forms从原Schema派生的fields_by_block_kind，明确code不允许空markdown占位。128000字节门禁覆盖全部新增载荷；没有截断上下文。原输出Schema字节、题量2–4/short_text、形式、生成/准入/评分权限和教学阈值不变。没有启用语义评分器或自动可靠答案资格；开放解释题仍可能结构合格，须由实际逐题复核识别其评分不适用，程序不擅自改写答案。原v2仍可从历史Git恢复，原事实不回写。

验证共158 passed，0skip：

- `cd backend && .venv/bin/python -m pytest tests/test_free_scene_answer_contract.py tests/test_free_scene_form_contract.py -q --junitxml=/tmp/edumind-t061-unit.xml`：23（新13＋原形式10）。包含中英文完整payload精确字节边界、过限零发送、跨kind空字段原样失败、初始/赋值后状态不同的合成追踪和显式理由选项。合成答案测试不代表真实模型正确。
- `python3 docs/acceptance/phase-1.5-answer-contract-t061/run_pg_offline.py`：新共存PG1＋原形式PG1＋原生成54＋准入40＋调度39＝135。各组新建专用库并保持原前缀保护；只有Mock生成/审核。真实旧v2生产者及原Schema从11d6909精确Git源码加载，v2/v3并存、原候选和digest不变、request_digest区分、幂等不重发、owner隔离、DB不可改写及不增加ready均验证。
- 两个旧测试只将准确Prompt版本期望v2改为v3，形式/拒绝/修复/持久性断言保持；原Schema及验证器未改。
- `.venv/bin/mypy app/agents/free_scene_generation.py`、五个修改/新增源文件Ruff、工作流/diff通过。代码自查完成，不冒充独立评审。
- 06ac4f9完整历史快照中运行r04结果checker，预期exit2，确认真实停止/unknown/固定分母仍有效。当前源码有意升级，不能改旧冻结SHA使其在新树冒充匹配。

首次新PG测试误复用已关闭session，虽断言通过但触发连接回收告警；已改为当前session仓储并重跑，最终新测试无此告警。旧生成测试仍有3条已存在的连接GC警告，Starlette弃用警告也如实保留，详见validation.json。专用PG容器已恢复exited。

真实调用0，无生产开放/旧批次恢复。T060完成11d6909，T061独立提交；T038继续blocked于尚未完成真实全槽诊断，r04原unknown不解除。下一步需在当前新源码上接线安全观测记录、冻结新准确执行包和独立时间/请求预算；本批准不授权任何真实运行。不push/merge/部署。
