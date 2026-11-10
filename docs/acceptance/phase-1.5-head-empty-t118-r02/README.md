# T118 r02 · 空链表头插独立窗口

r01 在隐藏密钥输入阶段被中断，入口写入 STOP，HTTP 尝试为 0。旧操作已收到取消请求，无课程版本。参见 [T118 统一结果记录](../phase-1.5-head-empty-t118/RESULTS.md)。

r02 为新的独立批次，使用 `head-empty-deepseek-r02`、专用库 `edumind_catalog_p15_t108_t118_r02`、新访客操作及新加密原件目录 `~/.local/share/edumind/head-empty-deepseek-r02`。原目录及 STOP 保留。执行与准入只接受对应批次、数据库、操作、批准与原件绑定。

[规划请求](planning-request.template.json)、[正文请求](teaching-request.template.json) 与 r01 模板字节一致，继续使用原 [T118 执行与审核规则](../phase-1.5-head-empty-t118/README.md) 和 [ADR0058 补充](../../ADR/0058-t118-empty-head-supplement.md)。运行时只填入本操作 UUID 和同批独立审核通过的实际规划。题干由模型生成，四题情境代码由程序装配。

- 本机准备命令为 `backend/.venv/bin/python scripts/run_head_course_goal_dev.py --profile empty-r02 --prepare --start`，目标页 [5210](http://127.0.0.1:5210/)，API 8190。提交准确目标后由数据库计时 30 分钟。
- 执行入口为 `backend/.venv/bin/python -m scripts.head_course_goal --profile empty-r02`。使用 `/tmp/edumind-t118-r02/env.json` 中的专用配置和本批 vault。先 `--prepare` 绑定操作，再按原规则进行 `--send plan`、独立规划审核、`--send generate`、独立全文审核和 `--publish`。密钥只在本机终端隐藏提示输入。
- [批准模板](approval.template.json) 默认未授权。[冻结清单](manifest.json) 绑定新批入口。拟议 DeepSeek 官方直连 `deepseek-flash`，规划 1 次、正文 1 次、修订 0 次，失败封存停止。新批窗口和 C2 例外待批准，实际留存及金额未确认，无费用硬上限。旧批额度不继承。
