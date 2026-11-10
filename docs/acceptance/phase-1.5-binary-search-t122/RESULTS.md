# T122 二分查找统一结果

2026-11-10 完成零调用准备。固定主例为升序数组 `[2,5,8,12,16]` 查找 5。初始化区间为 `[0,4]`，依次缩到 `[0,1]`、`[1,1]`，返回零基下标 1。更新帧保留刚用过的 `mid`，并显示其已排除。未找到时以区间为空退出并返回 -1。重复值边界已用固定 C 函数独立核对。[逐帧和四题独立预期](independent-reference.json)

| 实际检查 | 结果 |
| --- | --- |
| 隔离 PostgreSQL 升级至 head，`pytest -q backend/tests/test_binary_search_course_trial.py backend/tests/test_course_trial_transport.py` | 5 项通过。Clang C11 独立核对六帧、两轮更新、两组迁移返回值、空与单元素和重复值。MockTransport 核对准确请求、越界预算拒绝、封存重放、错候选审核拒绝、单次发送、私有 v2、四题反馈及隔离 |
| `pnpm typecheck` 与 `pnpm exec vitest run tests/course-visualization.spec.ts tests/head-course-status.spec.ts` | 类型检查和 14 项测试通过，包括区间内外、刚用过的中点、逐行高亮及错误区间拒绝 |
| 隔离库 Chromium，`/tmp/edumind-t122-offline/seed-browser-fixture-final.py`、`check-browser-final.py` | 夹具 v2 的七个阅读块、六帧及 C 第 4、10、13、10、11、8 行、播放暂停、前后步与重置通过。四题全错和全对分别反馈 0% 和 100%。提交前答案隔离，其他访客读取场景和作答返回 404。刷新恢复场景、作答和输入，重复提交 0，页面错误 0。夹具摘要 `be0e93c93ea76551c8ea580263e755dc82345e2b513dc54880e8210fffa94f66` |
| 共用入口分别 `replay --topic head/stack/queue/queue-revision` | 四份历史候选按原冻结提交严格重放。队列修订的冻结读取器随共用入口演进绑定到其完成提交 |
| 本机入口、定向 Ruff、工作流、Git 差异与冻结核对 | 开发 Web 5216 和 API 8196 就绪，通用生成 POST 返回 409。`inspect --topic binary-search` 通过。请求 9,850 字节，SHA-256 `8600a1eac246169447fb6fa233da960931595b361aa6ea9c36531105f9c93ad4`，清单 SHA-256 `98f008aa94403b03c85fbd384eaf3e9903c7d4671b15422c145f802a2f7baaee` |

本步 Provider 请求 **0**，真实操作及窗口尚未建立。拟批准新 30 分钟窗口和一次 DeepSeek 首稿，规划、修订、重试和回退均为 0。通过候选绑定的独立全文审核后，才进入 [实际本机课程入口](http://127.0.0.1:5216/) 完成真实课学习验收。本记录继续承接实际授权、原件摘要、审核与交付结果。[准确执行包](README.md)
