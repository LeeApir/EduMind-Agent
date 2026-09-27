# T036：流式正文空白无损修复（非计费）

基线b496c3d，MVP0.2独立任务。T032继续blocked。0真实Provider调用，
不读取或修改真实.env，不切模型，不改变画像/路径时序、owner/幂等或审核发布。

## 全链核对

| 层 | 文本处理 | 判断 |
| --- | --- | --- |
| Responses adapter _sse_data | UTF-8跨字节重组，去协议CR/LF及data冒号后最多一个协议空格，join多行data | 处理外层SSE；JSON内空格/转义换行/缩进不被裁剪 |
| _stream_event/stream_text | output_text.delta原字符串；空字符串返回None；非空字符串truthy | 空格/换行字符串保留；reasoning/metadata/心跳不作为正文；完成状态检查不变 |
| Beta adapter正文 | 委托同一Responses adapter | 同样无损，不动结构化工具调用 |
| ProviderGateway.stream_text | 原样yield TextDelta，finally关闭 | 无strip、插入分隔或重排 |
| learning_sessions._first_screen_events | 原条件delta.text.strip() | **真实丢失位置**：独立纯空白chunk被整段丢弃；文字内空白混合chunk原本保留，故结果依赖切分方式 |
| _event | json.dumps编码delta，正文换行变JSON转义 | 可逆编码，不混淆SSE空行边界和正文空行 |
| web/api/learningSessions.ts | UTF-8增量解码，去协议末CR/data字段一个空格，JSON.parse | 不trim正文；token不做生命周期去重，重复空格也保留 |
| App.vue | stringValue验证类型，temporaryText += delta | 无正文trim；goal.trim只用于目标提交，不是正文 |
| LearningProgressPanel | temporaryText.trim只作是否展示判据；插值渲染原文本 | 不写回裁剪值，但原p默认white-space:normal造成**显示折叠** |
| acceptance/first_screen_v2 | 外层event/data strip后JSON解码；delta.strip只判断任意非空token计时，仍无条件feed段落 | 纯空白会影响候选边界，但不会冒充非空正文token；候选strip/去换行是评审摘要规范化，非原始全文 |

非流式Responses输出以空串join parts不插入字符；structured JSON后缀strip只是错误诊断，
目标URL rstrip、reason rationale strip、表单profile/quiz trim均不在正文传递路径。
无正文协议事件 ≠ 空字符串delta ≠ 纯空白delta。前两者不提供正文，第三者提供真实字符。

## 修复

SSE只排除delta.text == ""，不再按strip结果排除。独立空格、tab、CR/LF、空行原样编码发送。
前端temporary-body使用white-space:pre-wrap和overflow-wrap:anywhere，DOM正文不重组，
继续Vue插值转义，不新增HTML/Markdown执行，不修补模型围栏或额外添加换行。
纯空白累计时仍展示空状态，不丢弃存储，随后正文到达会连同原空白呈现。
CSS视觉软换行不修改textContent，不承诺Markdown高亮；现有临时文本展示语义不变。

## 回归与实际证据

backend/tests/test_learning_sessions.py新增三个不同正文切分：整段、逐字符、每3字符。
中文/前后空格/独立空格/独立换行/空行/tab/4空格缩进/列表/表格/拆分```围栏全部覆盖。
真实DeepSeekResponsesAdapter使用httpx.MockTransport，Provider SSE按单字节分片，
UTF-8中文跨传输chunk；附心跳、reasoning、metadata、空字符串事件。
经真实Gateway与真实应用路由/隔离PostgreSQL，token列表精确等于非空输入delta，
拼接结果逐字符等于原始正文；reasoning未泄漏，正式资源仍走原schema/审核流程。

mvp-0.2-t036-offline-sse.json是该测试产生的**离线fixture**，仅固定公开测试正文，
所有operation ID改成mock-operation；不是T035补造的真实原始流，没有历史时间数据。
生成命令（backend，文件已有则不能覆盖，复现需新的输出路径）：

```text
EDUMIND_LOSSLESS_FIXTURE_OUTPUT=<new-output-path> EDUMIND_TEST_DATABASE_URL=<isolated PG> uv run --frozen pytest -q tests/test_learning_sessions.py tests/test_first_screen_v2.py
```

web/tests/streamWhitespace.spec.ts直接读取上述实际后端SSE编码fixture，分别按1/7/65536
字节切分，经真实parseSseStream/startLearningSession重建一致（重复token不去重）。
mock fetch →真实App→LearningProgressPanel的DOM textContent与输入严格一致；
不用会trim的wrapper.text()作为全文断言。验证pre-wrap样式声明；未做真实浏览器视觉验收。

测量器新增独立空格/拆分双换行：首正文字符在t=10，单换行t=20尚未完成，
第二换行t=30完成；拆分代码围栏和缩进被候选排除，后段流结束t=60才完成。
这些是受控测试时刻，非模型实测时刻；候选规则/资格评审未改，编号或成员句点不自动放行。

## 样本1能否解释

只读T035 raw中的10个public_text候选，并逐项校验SHA；逐字符重建每个已保存候选仍一致。
原始Provider chunks、完整正文、代码围栏区被排除的内容、候选外空白及每chunk时间均缺失。
候选本身还经过评审摘要strip，不足以拼接成无损全文，更不能倒推原始分片或首次段落时延。
实际保存的候选3两项粘连、候选9残留围栏可核对；已证实旧代码会丢纯空白，
但不能证明这两处异常具体丢了几个换行，也不能排除模型生成异常Markdown。
样本1的列表编号/表格成员句点缺真实句末标点也是独立资格问题，传输修复不让它们自动通过。
test_saved_public_sample_one_is_partial_evidence_not_lossless_replay再次确认原decisions仍未确认。
**未回填任何历史raw/audit/decision，也没有补造chunks、时间或改成真实样本通过。**

## 实际验证与交接

- 隔离EDUMIND_TEST_DATABASE_URL uv run --frozen pytest -q：426 passed，0skip，9既有警告。
- uv run --frozen ruff check app tests ../docs/acceptance：通过；初次新测试长行/排序已修正。
- uv run --frozen mypy app：55源文件通过。
- pnpm --dir web test --run：70 passed/12文件；最终DOM格式调整后针对性4再次通过。
- pnpm --dir web typecheck/build：通过；lint初次新增单行p导致69警告，改多行后回到既有67、0错误。
- git diff --check，明确路径暂存并自查；旧恢复测试断言不变，仅Ruff机械排版变化。

本轮无损传递及计时回归已满足文本完整性复测前置条件，但不证明正式20样本性能通过。
未来采样要冻结本修复后的commit/模型/指令，保留全部候选与人工评审、240总预算和异常立即
停止保护，并取得独立执行授权；20样本入口的异常即时熔断仍需核对，不能把T035专用36上限
当240正式服务已具备相同保护。本轮不扩展计费采样工具任务，不调用真实模型。
画像串行和独立正文token2秒门槛未解决，T032继续blocked，不具备阶段切换条件。
交接：只创建T036本地完成提交；不push/merge/归档/进入MVP0.3。
