# 二分查找程序帧说明版单次验证

## 准备结果与待批准范围

接线已完成。真实 Provider 请求 **0 次**，尚未登记真实窗口、创建真实候选或验收浏览器课程。拟批准 **0 次规划、1 次新正文、0 次修订**，无重试及回退。

| 冻结项 | 值 |
| --- | --- |
| 批次 | `binary-search-program-frames-r01` |
| [清单](manifest.json) SHA-256 | `2387f3388a9f8893c6719d49194ea35b68d4527d75c0d7e31225649c728ef5fc` |
| [请求原文](request.json) SHA-256 | `dbb0be19be89d79e49609e3102b800c150df83d749bcd4bb7c706c2bcda8e58d`，11,413 字节，与 T129 冻结摘要一致 |
| 材料摘要 | `48be1b8fc2a40c0f72d73d55ccaa6b073adc2d779588ad89cb4d3936f2d095f7` |
| 请求参数 | DeepSeek 官方 `POST /responses`，`deepseek-flash`，`temperature=0.2`，`reasoning.effort=none`，`stream=false`，`store=false`，`max_output_tokens=4000` |
| 请求范围 | 固定提纲、C 代码、程序事实、六帧和四题情境及参考答案。模型输出为 `paragraphs`、`questions`、`summary`，由闭合 Schema 拒绝 `step_notes` |
| 时间边界 | `prepare` 创建新操作时登记起止时刻，相隔 1,800 秒；发送前预留 90 秒 I/O 超时。发送、响应和私有准入都受操作窗口限制 |
| 费用及保管边界 | 最多 1 次 HTTP；本地严格接受最多 139,264 输入 token 和 4,000 输出 token 的回报，接受阈值无法限制服务端计费。金额未知，无可验证的硬费用上限。停止后在途请求仍可能迟发或计费。本机原件无独立抗回滚保护，服务端保留情况未独立验证 |

[ADR0064](../../ADR/0064-binary-search-program-frames-trial.md) 集中记录上述 C2 决策。当前 [批准模板](approval.template.json) 不能启动批次。

## 执行入口与停止

在项目根目录、既有专用本机开发数据库配置下运行下列共用命令。实际发送须在用户批准后，核对提交、清单、请求和 C2，写入本批独立批准记录，准备本机访客并登记窗口。沿用 `edumind_catalog_p15_t127_reuse` 数据库，使用新课程、操作和原件目录。需将开发 API 重载到本提交，以读取新来源契约。

```sh
export PYTHONPATH=backend:.
backend/.venv/bin/python -m scripts.course_trial inspect --topic binary-search-program-frames
# 准确批准后，使用本次登记的 OWNER 和 APPROVAL：
backend/.venv/bin/python -m scripts.course_trial prepare --topic binary-search-program-frames --owner "$OWNER" --approval "$APPROVAL"
backend/.venv/bin/python -m scripts.course_trial send --topic binary-search-program-frames
backend/.venv/bin/python -m scripts.course_trial replay --topic binary-search-program-frames
backend/.venv/bin/python -m scripts.course_trial publish --topic binary-search-program-frames
# 首次结构、教学、准入或结果未知时停止：
backend/.venv/bin/python -m scripts.course_trial stop --topic binary-search-program-frames
```

发送只在本机终端隐藏提示中输入凭据。原件目录 `~/.local/share/edumind/binary-search-program-frames-r01/`，保留确切请求、尝试记录、加密响应、回执、候选、审核、准入或失败和停止标记。发送后的一次性 STOP 允许合格候选接受审核与准入；显式停止产生 HALT 并禁止准入。失败或结果未知时保留具体原因，结束本次验证。旧批次的批准、额度和审核均不适用。

## 全文审核与课程验收

审核前，从严格回放通过的候选读取原始教学字段，用 `app.services.binary_search_course_frames.assemble(raw_output, {})` 生成本地审查视图。独立审核核对五类绑定材料，包括正文及引用、同轮比较与区间更新、代码高亮和程序六帧、四题条件及解析、返回边界。重点检查正文有没有把同一轮的比较写成上一轮，以及更新帧有无被描述为重算 `mid`。

审核写入本批 `review.json`，绑定本次 `candidate_digest`，`parent_digest=null`，`full_lesson_reviewed=true`，并记录独立评估人、结论、阻断项和各检查结果。新增必检项为 `lesson_prose_matches_program_iterations`。窗口内仅允许独立全文通过的候选准入。页面使用「DeepSeek 新正文 · 程序生成帧说明」来源，保留本批请求、响应、候选、材料和审核绑定。

准入后实测阅读、六帧状态及行高亮、播放暂停和前后步重置、四题错误与正确反馈、提交前答案隔离、跨访客 404、刷新恢复同版且无重复提交。获准后将实际窗口、用量、审核、失败或课程入口和浏览器证据补入本记录。

## 零调用验证

- 专用 PostgreSQL 测试库与 MockTransport 定向 **6 项通过，0 跳过**。拒绝错请求、错额度、真实与夹具授权混用、规划或修订阶段、重发、T129 旧审核及缺失本批全文检查的审核。实测新候选绑定当次请求、响应、材料及审核，六帧和程序说明出现在 v2 私有场景。场景答案隔离及跨访客 404 通过。
- 模型额外返回 `step_notes` 的夹具按 `ROLE_SCHEMA` 拒绝，原响应可从封存精确解密，保留失败和 STOP。第一次执行测试时断言误用了 `SnapshotError`，调整为入口实际的 `PilotError` 后复验通过。
- 定向命令为 `pytest -q backend/tests/test_binary_search_course_frames.py backend/tests/test_binary_search_program_frames_trial.py`。测试进程加装既有 `raw_io_audit`，Provider 流量只经过 MockTransport。另核对 CLI inspect、禁止的阶段选项、T129 原件只读派生、Ruff、Vue 类型及 Git 差异。
