# 单次B局部修订：零调用定向检查

2026-11-05。执行者Codex；本记录不代表真实模型或教学重评通过。

- `PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q backend/tests/test_head_b_local_revision.py -k 'not private_import' --tb=short`：14 passed。准确父/证据/两项Schema，原段文字保持示例，strict合并、原payload只增证据、其他raw不变、统一重装配；缺/多/错字段、旧ID、邻段复制、错父及代码/轨迹/证据漂移拒绝。实际单次入口MockTransport成功并从加密原件回读；未知phase/重复键/4001输出token拒绝、保留原件/STOP/ACTIVE，再次发送拒绝。
- 专用T108本机PG最小测试配置：同文件`-k private_import --tb=short`：1 passed。MockTransport结果绑定证据与独立pass夹具，沿原仓储/准入导入新私有子课程并幂等读取；API源/parent/evidence一致、作答前无answer_key/solution、四题正确比较为100%且course_only、scene/feedback重复读取相等，child操作finite_head_foreground/budget=null。夹具明确offline_fixture，未计真实教学成功。该项不冒称实际浏览器完整学习验收。
- 复用入口改动相关旧 `backend/tests/test_head_course_fact_revision.py`：11 passed，旧四字段协议和请求/合并/实际入口拒绝行为保持；不重复其余无关回归。
- 三个变更业务源`mypy --follow-imports=silent`通过；变更Python Ruff通过；`pnpm --dir web build`含vue-tsc通过，变更前端ESLint通过。首次ESLint仅新段落换行两条warning，纯格式修正后无warning。
- `scripts/prepare_head_b_local_revision.py --check`与`head_course_fact_revision.py --profile evidence --inspect`核对实际请求构造/所有来源及冻结字节，当前prepared_not_authorized/Provider0。精确manifest见本包manifest.json；历史r01/证据T110/T108原件及冻结规范不改。

模型响应夹具只在测试临时目录存在，不是可交付修订稿；没有把助手文字写成新候选。当前不建真实vault、不启动窗口、不索取Key、不改原教学或发布真实课程。获得真实稿后，必须再独立全文重评及实际应用学习/四题/刷新验收。
