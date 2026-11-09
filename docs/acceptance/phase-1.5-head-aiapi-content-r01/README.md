# AIAPI 有限课程生成试验 · 待真实调用授权

批次 `head-fixed-aiapi-content-r01`，响应规则 `head-aiapi-content-responses-v1`。本批只验证 AIAPI 能否生成一份通过本地校验和独立教学审核、可在应用中完成学习的课程。请求模型为 `gpt-6.1-sol`，实际模型及未回显的执行参数记为未知。本批结果只适用于这次路线验证，不用于严格控制参数的模型对照。

本包已实施，真实授权为 0。T113 在原固定 Provider 契约下的判断和历史 `AIAPI_ENVELOPE`、STOP 继续有效。ADR0057 的导入资格只覆盖原 r05 候选，新结果须通过本批规则进入现有私有课程流程。[T113 评估](../phase-1.5-fixed-provider-t113/README.md) · [r05 结果](../phase-1.5-head-fixed-aiapi-r05/RESULTS.md) · [ADR0057](../../ADR/0057-reviewed-archived-head-import.md)

## 唯一请求和来源

| 项目 | 拟冻结值 |
| --- | --- |
| 请求 | `POST https://aiapi.world/v1/responses`，`Content-Type: application/json`，`Accept-Encoding: identity`。由本机前台入口提供 Bearer 凭据。发送 [request.json](request.json) 的原始字节，摘要见 [manifest.json](manifest.json)。 |
| 配置 | `model=gpt-6.1-sol`、`stream=false`、`store=false`、`temperature=0.2`、`max_output_tokens=8000`、`reasoning.effort=low`。无工具、后台执行或上游会话。 |
| 相对 r05 的请求差异 | 仅将 `reasoning.effort` 从 `none` 改为 `low`。`low` 曾出现在 r04 回显中，本次是明确请求值，服务端支持和实际执行待本次验证。提示词、用户材料及 `edumind_head_goal_course` strict JSON Schema 逐字段一致。 |
| 复用规划 | r05 实际使用的 T111 r01 已审规划 `0997615b…` 和程序材料 `854939ff…`。复核原规划请求、响应、独立审核和材料及教学证据摘要。`head-new-C` 从 `[5]` 插入 `-2、9`，主轨迹 13 帧，对照为两次忽略返回后仍遍历 `[5]`。 |

原请求里的 `source_binding` 是同一历史样本的三个不透明课程、操作和请求 ID，随原材料冻结。它们只用于来源核对。新应用的 owner、课程、操作与审核另行绑定到本批原件；运行入口必须验证新旧目标和程序材料一致，并禁止写回历史操作。请求不含真实学生档案、凭据或作答。[原规划审核](../phase-1.5-head-fixed-live-r01/plan-review.json) · [r05 请求绑定](../phase-1.5-head-fixed-aiapi-r05/approval.json)

## 响应兼容和停止条件

分别保存请求值、响应字段是否存在、响应原值及判定。缺失项保留未知；匹配回显也仅代表服务端报告。先封存收到的原始字节，再解析和验收。

| 项目 | 可接受的范围 | 停止条件 |
| --- | --- | --- |
| 模型、存储、温度、输出上限 | 各字段缺省记未知。出现时分别须为 `gpt-6.1-sol`、布尔值 `false`、数值 `0.2`、整数 `8000`。已观测的 `max_output_tokens: null` 记为上限未回报，保留与缺省的区别。 | 错值、错类型，或其他非约定的 `null`。 |
| 推理与用量 | `reasoning` 可缺省，出现时只接受 `effort=low`，以及可缺省的已知回显 `context=all_turns`、`mode=standard`、`summary=null`。`usage` 的输入、输出、总数须为非负整数且输入加输出等于总数。推理 token 缺省记未知，报告时允许 `0 ≤ reasoning_tokens ≤ output_tokens`，计入输出且不重复加总。缓存及模态明细只作原件记录。 | 推理回显冲突、用量缺少主计数、计数无效或超过本地验收限额。非零推理计数本身可通过，独立推理输出项仍停止。 |
| Schema 回显 | `text.format` 的类型、名称、`strict=true` 及 Schema 必须等于原请求。唯一允许差异是回显删除 `/properties/paragraphs/items/properties/fact_ids/uniqueItems`。 | 缺失整个回显、改动该值，或出现任何其他增删改。始终用原请求内的完整 Schema 校验正文，重复 `fact_ids` 拒绝。 |
| 指令与执行 | `instructions` 缺省或 `null` 记回显不可用，存在文本时必须与原 system 文本完全相同。`tools` 可缺省或 `[]`，`background` 可缺省或 `false`，`previous_response_id` 可缺省或 `null`。 | 追加或替换指令，包括已知 r04 后缀。非空工具、工具输出或非零工具用量、后台执行、会话继承、未知执行字段均停止。 |
| 完整响应 | HTTP 200，收齐非 SSE 响应，编码为 identity（可缺省），外层 `object=response`、`status=completed`。仅一条 `assistant` 的 `completed` 消息，仅一个非空 `output_text`。`phase` 可缺省或为 `final_answer`，`annotations`、`logprobs` 可缺省或为空数组。若有顶层 `output_text`，须逐字等于消息正文。 | 非预期 HTTP 状态、状态冲突、多个输出、空正文、不同副本、未知输出类型或非空注解。 |

其余允许的元数据仅为响应和消息的非空字符串 `id`、响应的非负整数 `created_at`/`completed_at`，以及缺省或与实际传输相符的 `stream=false`。`error` 和 `incomplete_details` 可缺省或为 `null`。用量明细仅识别 r05 已见的 `audio_tokens`、`image_tokens`、`text_tokens`、`cached_tokens`、`cached_creation_tokens`、`cache_write_tokens`、`reasoning_tokens`，出现时须为非负整数，非零音频或图像计数停止。未列出的字段停止。回显内容及关联标识仅留在私有原件。[封存回显对照](../phase-1.5-fixed-provider-t113/observations.json)

停止时保留具体原因和原件状态：

- `incomplete` 或明确的不完整原因记为不完整，只有原因指向长度上限时记为服务端报告截断。自报输出恰为 8,000 时记「存在截断疑点」，结合终态、收包和结构分别记录。本批即使其余检查通过也保守停止，截断仍未确认。超过 8,000 记超限。
- 显式 `refusal` 记拒绝。非 200、失败终态、非空 `error`、非法 JSON 或容器冲突各记对应的 HTTP、服务端或协议失败。保留完整错误体，能安全区分拒绝时单独标记。
- 超时、断连、响应超字节限或原件无法完整回读时停止。有多少可安全封存的响应字节就记录多少，并标明部分响应或原件未知，不能标记完整。未收到可靠终态时，服务端结果和费用仍未知。

## 时间、费用和封存

| 项目 | 本批提案 |
| --- | --- |
| 次数 | **0 次规划、1 次新正文、0 次修订**。只允许一次出站尝试，发送前占用额度。无重试、重定向、回退或额外探测，历史额度为零继承。 |
| 时间 | 审批和入口就绪后登记新应用操作创建时间，共用截止为该时间加 **1,800 秒**。开始发送须至少剩 300 秒。读取 I/O 超时 **300 秒**，连接、写入和连接池各 **90 秒**，共同受绝对截止约束。到期、取消或未知结果停止发送及写入新准入。截止后可只读核对已存证据或已准入课程。 |
| 本地限额 | 请求正文最多 131,072 字节，响应最多 2 MiB。输入用量本地预约和验收上限 **139,264 token**，输出请求值和本地验收上限 **8,000 token**，推理计入输出。报告输入超过预约或输出超限时停止。这些限额不能约束服务端实际执行或撤销计费。 |
| 费用边界 | 一次尝试限定调用次数。若有可核实的 AIAPI 计费表，以 139,264 入、8,000 出为计算口径，按计费表处理推理和缓存，避免重复计数。本包没有经确认的 AIAPI 金额估算。实际金额以账单为准，无可验证的硬上限；前台停止后仍可能完成或计费。 |
| 封存 | 发送前绑定批准记录、请求摘要、时间窗、入口版本及新操作。使用独立本机私有原件库和一次性出站标记。记录请求、HTTP 收据、加密原始或部分响应、字节摘要、完整性标记、用量、判定、审核和终止记录。凭据仅从终端隐藏输入，不进证据。完成或失败均关闭出站。本机原件没有独立抗回滚保障。 |

## 课程准入与评估交接

用完整原请求 Schema 检查严格 JSON，复核事实引用、四题情境代码的精确绑定，以及同版轨迹、代码和参考答案。沿用 [T111 全文审核与学习验收](../phase-1.5-head-fixed-t111/review-policy.md) 的通过要求，逐段、逐帧、逐题评估。首稿任何失败即封存停止，无格式恢复、补写或修订。通过记录须绑定新请求、响应、候选、复用规划、材料及教学证据摘要。

四题的情境代码逐题匹配程序源码。接受完全一致，或仅少源码末尾一个 LF。匹配时比较原题干的代码后缀，禁止剥除其他空白或改写原始响应、正文、候选和答案。内部字符、CRLF、额外 LF 等其余差异均停止。该例外仅属于本批响应规则，教学审核沿用同一标准。

独立审核通过且仍在窗口内时，按新操作绑定写入现有私有版本库。页面注明 AIAPI 试验来源、请求模型和回显未知项。验收全文阅读、13 帧状态与代码高亮、播放控制、四题服务端反馈、答案隔离及刷新后恢复同一版本和作答。分别记录响应是否合格、本地校验、独立教学审核和浏览器验收。

真实调用授权应集中确认以下三项。

1. **试验目标和允许差异。** 接受实际模型及缺失参数未知、可报告非零推理、只允许一处 Schema 回显缺项，以及触顶保守停止。请求内的 `store=false` 不能承诺服务端零留存；批准范围仅含这份固定开发样本和其历史来源 ID。
2. **一次尝试的费用与停止边界。** 确认 30 分钟窗口、各项 I/O 超时、字节和 token 口径。若必须事先核定金额，缺少可靠费率时不发送。若接受金额未知，则一并确认 C2 例外，即迟发或继续计费风险、无可验证金额硬上限及本机原件无独立抗回滚保障。
3. **准入边界。** 入口以新操作保存已审旧规划为 v1，发送前从新操作读回规划、目标和材料，独立审核通过后按原私有准入和写入围栏保存 v2。真实发送绑定本包、入口和请求摘要，以及实际操作与窗口。

## 实际入口与离线验证

在仓库根目录用 `PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.head_course_aiapi_content inspect` 核对请求、入口和包的 SHA-256。请求保持 35,665 字节，SHA-256 为 `4df87d4a2ab296d1deb4e1ae67ebe35bda0eceb02f3a548ab69cc172184409b5`。

获本批真实调用授权后，沿用 `backend/.venv/bin/python scripts/run_head_course_goal_dev.py --profile aiapi --prepare --start`。应用入口为 `http://127.0.0.1:5206/`，只使用本批隔离开发库。前台入口从该开发配置读取数据库连接，使用 `scripts.head_course_aiapi_content` 的下列子命令。

| 子命令 | 操作 |
| --- | --- |
| `prepare --owner <新访客 UUID>` | 创建本批新操作和 v1 大纲，登记 30 分钟窗口，返回待绑定字段。准备阶段没有模型请求。 |
| `approval-fields` | 读取待绑定字段。取得明确授权后才将这些字段连同 `explicit_user_authorization=true`、`accept_batch_C2=true` 写入私有原件目录的 `approval.json`，权限 0600。 |
| `send` | 校验授权和实际操作，在终端隐藏输入凭据。唯一出站尝试封存后写 STOP。 |
| `review-input` | 回读原件，生成独立审核输入。审核须在原标准字段之外原样带回 `aiapi_binding`，其中包含操作、请求、原始响应、规划及材料绑定。 |
| `publish --review <独立审核文件>` | 在窗口内重放原件和审核，走现有私有课程准入。 |

入口使用本批私有目录 `~/.local/share/edumind/head-fixed-aiapi-content-r01/`。开发启动器把本批数据库配置保存至 `/tmp/edumind-head-aiapi-content-r01/env.json`。需要在终端运行子命令时，可从仓库根目录用本地启动器配置加载入口，将末尾的 `inspect` 替换为对应子命令。

```sh
backend/.venv/bin/python -c 'import json, os, runpy; from pathlib import Path; os.environ.update(json.loads(Path("/tmp/edumind-head-aiapi-content-r01/env.json").read_text())); runpy.run_module("scripts.head_course_aiapi_content", run_name="__main__", alter_sys=True)' inspect
```

在专用 PostgreSQL 中运行 `pytest -q backend/tests/test_head_course_aiapi_content.py scripts/tests/test_diagnose_head_course_t115.py backend/tests/test_head_course_deepseek_wire.py 'backend/tests/test_head_course_reuse.py::test_actual_entry_and_private_application[direct]'`，**53 项通过，0 项跳过**。Provider 传输使用 HTTPX MockTransport 和固定测试地址，历史 DeepSeek 回归只读封存原件。检查覆盖回显差异与异常、原 Schema 拒绝重复引用、T116 末尾 LF 边界、错误审核拒绝、私有 v2 及四题服务端反馈。另验证了未授权、已有尝试记录、剩余不足 300 秒、到期发布、读超时保留部分响应及 STOP 后再发拒绝。

Ruff、Web 类型检查、任务账本和 Git 差异检查通过。真实调用仍为 0，实际 Provider 回显、生成质量、真实浏览器学习流程及账单待本批获准后验证。
