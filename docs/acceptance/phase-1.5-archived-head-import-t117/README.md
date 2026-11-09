# T117 · AIAPI content r01 封存正文学习交付

在同一本机访客会话中打开 [学习入口](http://127.0.0.1:5202/)，在「继续你的学习」进入头插课程。已在交付浏览器打开 v2 并刷新确认来源，候选为 `633091fd1c05ab83212c0f0256024bb7422021ef2d044e890e88ad72f9cc2412`。同一访客重复导入返回同一版本。验收作答使用隔离的测试访客。[交付课程绑定](app-binding.json) · [浏览器验收记录](browser-results.json)

本批沿用现有导入 CLI、原子事务、私有版本与服务端练习，新增一个经批准的固定来源。原样提取的 13,176 字节正文重新通过原请求 Schema，四题情境代码逐字节匹配。正文、主例代码、轨迹和答案与已审候选一致。新页面显示 AIAPI content r01 封存正文导入、独立审核通过，以及请求模型、响应标签和 `store=false` 回报。实际模型和留存状态未确认。[补充提案](../../ADR/0057-aiapi-content-r01-import-supplement.md) · [授权记录](../../ADR/0057-aiapi-content-r01-import-approval.json) · [全文审核](../phase-1.5-head-aiapi-content-r01/ASSESSMENT.md)

- Chromium 核对了 10 个阅读块及主例代码，逐帧核对 13 帧状态、文字与高亮行。播放、暂停、前后步和重置通过。
- 四题各做一次错误及正确提交，反馈匹配率分别为 0% 和 100%，逐题解析与审核正文一致。课程场景响应隔离答案和解析，另一访客访问场景及作答均返回 404。
- 整页刷新恢复同一课程版本、四个输入及反馈，作答 POST 总数仍为两次。数据库检查确认重复导入幂等、就绪写入后故障可回滚，模型发送计数为零。
- 两种授权来源均通过公开契约校验，错批、错候选、错存储值及错材料摘要被拒。旧 r05 按默认 CLI 路径保留资格。冻结执行包的运行源码摘要在历史提交 `559fbdd` 上逐项复算通过。

原生成操作只读复核为 `failed / HEAD_AIAPI_ENVELOPE`，仅有 v1 大纲。原件、STOP、参数冲突及历史用量均以原批收据为准。此次导入新增 Provider 调用为 **0**。[原生成终态与协议差异](../phase-1.5-head-aiapi-content-r01/live-result.json)

本次浏览器命令如下。

```sh
backend/.venv/bin/python scripts/check_head_course_archive_browser.py --source head-fixed-aiapi-content-r01 --artifacts /tmp/edumind-t117-checks
```

验收调用既有 `scripts/import_head_course_archive.py --owner <访客 UUID> --source head-fixed-aiapi-content-r01`，使用本机 archive profile 的专用数据库配置。Ruff、Web 类型检查、任务账本和 Git 差异检查通过。
