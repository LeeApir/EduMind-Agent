# T112 · 封存正文限定导入与学习交付

本机应用 [http://127.0.0.1:5202/](http://127.0.0.1:5202/) 已打开交付课程。当前浏览器的同一私有学习身份也可从「继续你的学习」进入。课程版本为 v2。开发访客会话到期后，可在新会话建立后按下列 CLI 重新导入。课程及场景 ID 见 [当前浏览器绑定](app-binding.json)。

页面标明「从已封存响应提取的正文，独立教学评估通过」。请求模型为 `gpt-6.1-sol`，实际模型和存储状态未确认。导入从加密原件读取同一条助手消息并严格解析，核对请求、响应、正文、候选、规划、共享材料和审核。教学正文未改写。私有候选存储原文、来源摘要和评估，零出站记账，原件继续保存在原私有库。AIAPI r05 的原响应拒绝 `AIAPI_ENVELOPE`、失败与 `STOP` 可按原件索引复核。[ADR0057](../../ADR/0057-reviewed-archived-head-import.md) · [原独立评估](../phase-1.5-head-fixed-aiapi-r05/ASSESSMENT.md) · [原件索引](../phase-1.5-head-fixed-aiapi-r05/originals-manifest.json)

- 实际 PostgreSQL 记录证实重复导入沿用同一课程及 v2，仅有一条导入候选及零出站记录。模拟就绪写入后的失败，课程、版本、操作、收据及候选均回滚。两个不同访客之间的场景和作答读取均返回 404。
- 实际 Vue 页的九个阅读块及代码与装配一致。逐一核对 13 帧状态、说明和代码高亮。前后步、播放、暂停和重置通过。
- 完成四题各一次错误与正确提交，匹配比例为 0% 和 100%。服务端反馈逐题等于审核正文的解析，公开场景无参考答案或解析。整页刷新恢复版本、四个输入和反馈，未新增作答提交。[浏览器检查记录](browser-results.json)

实际执行命令

```sh
backend/.venv/bin/python scripts/run_head_course_goal_dev.py --profile archive --prepare --start
backend/.venv/bin/python scripts/check_head_course_archive_browser.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

浏览器检查脚本在开发库新建测试访客并调用 `scripts/import_head_course_archive.py --owner <现有访客 UUID>`。CLI 使用本机开发配置，由开发启动器写入 `/tmp/edumind-t112/env.json`，该文件不入库。用准确 r05 响应重放旧协议拒绝。分别用伪造模型、存储状态和候选摘要检查新来源投影拒绝。T107 原 C01/C02 映射仍通过，原入口拒绝 r05。历史 T111 冻结包在 `93456b2` 上复算 410 项一致。

本次实际 Provider 调用为 0。交付证据归属 T112。T111 的固定方案端到端验收及 T038 的阶段门禁仍按各自契约记录。
