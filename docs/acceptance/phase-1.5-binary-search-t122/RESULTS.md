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

## 真实首稿和停止

用户批准 `955c15b`、准确清单及本批 C2。本批北京时间 22:50:13–23:20:13。执行 1 次 DeepSeek 首稿，规划、修订、重试和回退均为 0。HTTP 200，服务端状态 `completed`，回报输入 2,649 tokens、输出 982 tokens。实际账单与服务端留存未独立核实。[批准登记](../../ADR/0062-t122-approval-20261110.json)

从加密原件复现 `ROLE_SCHEMA`。四题 `increase_left`、`decrease_right`、`found_index`、`missing_result` 都只有 `stem`，缺少必填的 `explanation`。按准确请求中的 Schema 逐项诊断，四处均违反 `required`。响应为完整保全，结构错误阻断候选生成和独立全文审核。[原件索引与诊断](live-result.json)

执行共用入口 `stop --topic binary-search` 并用现有恢复流程收尾。请求、加密响应、失败记录、STOP 与 HALT 封存。使用 `/tmp/edumind-t122/verify-stopped.py` 在原访客 Chromium 会话确认操作为 `cancelled`，仅提纲 v1、就绪场景 0，v2 场景返回 404。实际课程未交付，真实学习验收未执行，T122 保持 blocked。

## 十字段修订准备

原稿只读核查确认四个缺失解析、四道带花括号的题干，以及 f2、f4 把本轮刚完成的比较称为「上一轮」。本次按用户指定范围冻结四个题干、四个解析和两条帧说明。题干使用程序指定的固定文本。模型负责四条解析和两条帧说明，并原样返回指定题干。原稿绑定原响应、原请求及同版材料摘要，新候选沿用原八项独立全文审核。[修订包](revision/README.md)

隔离 PostgreSQL 与 MockTransport 定向测试 7 项通过。覆盖越界键、改动题义的题干、错误轮次、范围外原稿差异、完整合并、审核门禁、私有投影和答案隔离。Ruff、工作流、封存源摘要和准确请求检查通过。新增 Provider 调用 0。独立全文重评、真实准入和浏览器验收待获准后执行。

请求 SHA-256 为 `9858b9a65751dde557de10908ec79179925025a431e10aa670d23c2e68404930`，清单 SHA-256 为 `31a46df3d46b0a8238b3e1fcbb0efdc81b160551b611a885bfc8c76f308b9ae2`。拟申请新窗口 30 分钟、1 次局部修订、0 次规划、0 次整课生成及本批 C2。原首稿拒绝、STOP、HALT 和已取消操作按原记录复核。
