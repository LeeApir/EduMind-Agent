# T127 四主题有限真实复用批次

当前实际 Provider 请求 **0**，实际窗口和授权均未建立。批准项集中见 [ADR0063](../../ADR/0063-four-topic-live-reuse-trial.md)、[冻结清单](manifest.json) 和 [未批准的记录模板](approval.template.json)。

## 固定输入与请求

| 顺序 | 固定开发输入与独立预期 | 规划和正文 |
| --- | --- | --- |
| 1 空链表头插 | `head=NULL`，两次成功分配，依次插入 4、7。接收返回后 `[7,4]`，忽略两次返回后调用者入口仍为 NULL，两新节点均不可达。13 帧。 | [规划模板](requests/head-plan.template.json) · [正文模板](requests/head-generate.template.json) · [独立材料核对](../phase-1.5-head-empty-t118/independent-reference.json) |
| 2 栈 | 初始空栈，`push(3) → push(8) → pop() → push(5)`。栈底到栈顶 `[] → [3] → [3,8] → [3] → [3,5]`，出栈 8。5 帧。 | 程序固定提纲 · [完整正文请求](requests/stack-generate.json) |
| 3 队列 | 初始空队列，`enqueue(3) → enqueue(8) → dequeue() → enqueue(5)`。队头到队尾 `[] → [3] → [3,8] → [8] → [8,5]`，出队 3。5 帧。 | 程序固定提纲 · [完整正文请求](requests/queue-generate.json) |
| 4 二分查找 | 升序 `[2,5,8,12,16]`，查找 5。零基闭区间 `[0,4]`，中点 2，值 8，收缩至 `[0,1]`。中点 0，值 2，收缩至 `[1,1]`，在下标 1 找到。6 帧。 | 程序固定提纲 · [完整正文请求](requests/binary-search-generate.json) |

每课的完整学习目标、示例和四题迁移材料来自对应构造器。程序持有代码、轨迹、事实、练习情境及私有答案。模型生成讲解、帧说明、题干、解析及总结。新二分首稿使用原主题 Schema，四个题干由模型生成。未向新首稿注入 T122 历史修订题干。

头插规划请求只用本批实际课程、操作及原目标请求 UUID 替换模板对应位置。无画像证据。正文只从该操作已封存并通过独立语义审核的规划构造。正文模板替换这三项 UUID 及规划占位，材料、目标、提示词和 Schema 保持冻结。头插用 `head-goal-planning-wire-v2` / `head-goal-plan-grounded-v3` 和原本地规划业务校验，正文使用 `head-empty-course-trial-v1`。栈、队列和二分首稿分别使用 `stack-lifo-course-v1`、`queue-fifo-course-v1`、`binary-search-course-v1`。四课首稿均显式使用 `course-question-stem-v2`，解释仍必填，事实引用和本地题干校验沿用原规则。

条件修订由 `shared-trial-limited-revision-v1` 从准确父稿、审核意见和允许路径生成闭合 Schema。运行前无法知道真实父稿和允许字段。通过 `inspect-revision` 查看完整动态请求及其摘要，将摘要写入准确修订记录后才可准备。规划、正文和修订的实际请求都以发送字节封存。运行期间清单中的代码、规则、提示词、Schema 和材料发生变化即停止，本轮复用验证失败。

## 调用、窗口与费用

| 阶段 | 头插 | 栈 | 队列 | 二分查找 | 合计 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 规划 | 1 | 0 | 0 | 0 | 1 |
| 正文首稿 | 1 | 1 | 1 | 1 | 4 |
| 条件修订 | ≤1 | ≤1 | ≤1 | ≤1 | ≤4 |
| 合计 | ≤3 | ≤2 | ≤2 | ≤2 | ≤9 |

固定 DeepSeek 官方 `https://api.deepseek.com/responses`，请求 `deepseek-flash`、非流式、`store=false`、`temperature=0.2`、`reasoning.effort=none`、strict JSON Schema。校验 `head-deepseek-responses-v1` 和 `limited-c-message-phase-v1`。无模型审核、自动重试、探测或回退。无修订且四课都交付时共 5 次。未知尝试占用其原槽，空余次数不转移。

建议本机整批窗口 5,400 秒，登记后即开始。每课操作从准备时起另有 1,800 秒，与整批期限取较早者。连续发起请求前检查至少还剩 90 秒。HTTPX 90 秒是各阶段 I/O 超时，墙钟可能更长。发送上限为每请求 128 KiB，收集上限 2 MiB。回执输入按每次 139,264 tokens 检查，九次预留共 1,253,376。规划和头插首稿输出上限各 8,000，其他首稿和条件修订每次 4,000，合计 44,000。输入数字是预留和回执校验边界，费用可能在收回或校验回执前已经产生。实际账单和可验证金额硬上限未知。仅记录服务回报及其置信范围，模型快照和服务端留存未经独立确认。

本批需明确接受 C2。停止是单前台尽力停止，可能迟发或继续计费。本机原件无独立抗回滚保障。审批须明确绑定本批清单摘要、专用访客 UUID、预算分配、窗口长度和 C2。旧批额度与批准不继承。

## 准备和执行

准确授权后，从仓库根用现有开发启动器启动专用库及本机页面。用本机访客会话取得同一所有者 UUID。此步骤不会发送 Provider 请求。

```sh
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_head_course_goal_dev.py \
  --profile live-reuse --prepare --start
```

[本机课程入口](http://127.0.0.1:5217/) 使用专用库 `edumind_catalog_p15_t127_reuse` 和 API 8197。该应用使用现有课程列表、播放器和反馈，禁止后台 Provider、普通新生成和继续操作。以下函数从启动器写入的私有文件读取专用库环境，不读取项目 `.env` 或使用环境变量中的 Provider 凭据。

```sh
trial() {
  backend/.venv/bin/python -c '
import json, os, sys
with open("/tmp/edumind-t127/env.json") as source:
    env = json.load(source)
os.execve(sys.executable, [sys.executable, "-m", "scripts.course_trial",
                          *sys.argv[1:], "--live-reuse"], env)
' "$@"
}
trial inspect --topic head
trial start-batch --approval "$APPROVAL"
trial prepare --topic head
trial send --topic head --stage plan
trial replay --topic head --stage plan
```

用 `start-batch` 返回的实际 UTC 起止时间登记窗口，再准备第一个主题。唯一原件根目录为 `~/.local/share/edumind/four-topic-live-reuse-r01`。每个主题有独立子目录，保留共享 `batch.json`、操作上下文、逐阶段请求、尝试记录、响应头、加密响应、正文回执和候选或失败。Provider Key 只在每次 `send` 的本机隐藏提示输入。头插正文前先将独立规划审核保存到 `head/plan-review.json`，绑定规划候选、规划摘要和示例依据，包含原空链表两个审核项。

```sh
trial prepare --topic "$TOPIC"  # 头插已在规划前准备，其余主题各准备一次
trial send --topic "$TOPIC"
trial replay --topic "$TOPIC"
trial publish --topic "$TOPIC"  # 已有绑定该首稿的 review.json 且独立全文通过
```

若 `review.json` 判为可修，准确修订记录沿用 T126 字段，增加 `run_sha256`（从候选 `context.live_run` 读取）并使用 `offline_fixture=false`。审核须定位原文或原引用、问题和段落职责，标记全文已审，且所有阻断都只是允许修订的次要措辞或引用。局部批准是在批次已批准的范围内确认动态请求。预览记录可用 `approved=false` 和 `request_sha256=null`，准备时准确确认请求摘要及一次额度。

```sh
trial inspect-revision --topic "$TOPIC" --record "$REVISION_RECORD"
trial prepare-revision --topic "$TOPIC" --record "$REVISION_RECORD"
trial send --topic "$TOPIC" --stage revise
trial replay --topic "$TOPIC" --stage revise
trial publish --topic "$TOPIC" --stage revise  # 已有绑定父子稿的 revision-review.json
```

只允许 `paragraphs[i].text`、`paragraphs[i].fact_ids`，头插的 `learning_summary`、`failure_scope`，或其他三主题的 `summary`。保持段落职责、必要解释和全文一致性，禁止复制邻段。代码、材料、轨迹、答案、题干、解析及帧说明均保持首稿字节所表达的值。初审通过直接准入。修订重新做机械检查和独立全文审核。先前主题只有在对应本批的 `published.json` 成功保存后才开放下一课。

规划失败、Schema 或协议不合格、重复键、缺字段、拒绝、截断、用量异常、传输未知、严重教学问题、超范围阻断或修订后仍不合格时停止整批。入口收到机械发送失败会标记整批 `HALT`。人工审核拒绝、遇到不确定或截止时保留审核与原件，运行 `trial stop --topic "$TOPIC"` 关闭整批并请求取消当前操作。已交付课可继续学习，未运行槽保留。无法在冻结版本完成时登记失败，批内不调整提示词、规则或补写原稿。

## 审核与课程验收

独立评估逐段、逐帧、逐题核对事实和引用、题目条件、答案唯一、没有泄漏和解析准确。头插核对作用域、首尾两次链接、分配/判空的演示范围、忽略返回值和资源生命周期。栈核对栈顶与出栈值、LIFO 和实现边界。队列核对 FIFO、队头队尾、出队值、单元素、重复数值与前移代价。二分核对升序前提、闭区间、当前轮中点、比较、终止和重复值边界。评估记录绑定实际候选摘要，修订重评另绑父稿。主题原有检查项和独立参考继续适用。

在有效窗口内完成每课私有准入。用原访客打开实际课程，核对全文及来源版本、逐帧状态与代码高亮、播放暂停、前后步与重置。对四道题核对全错和全对的反馈及解析，检查提交前私有答案未随课程返回、其他访客不可读取，刷新恢复同一课程版本和已有作答且无重复提交。记录每课从准备到完整就绪的耗时供诊断，并保留失败和未运行槽。

执行后统一记录为本目录的 `RESULTS.md`。按四个预分配槽逐行记录首稿结构、首次教学、格式恢复（本批禁用）、条件修订、最终审核、学习入口和浏览器证据。逐阶段记录实际尝试与可核验的回报用量，未知单列。附原件摘要、失败码、规划与候选、独立审核和最终页面版本的绑定。四课均通过才记本批通过。样本已用于开发，本结果不计为 T038 或独立未见样本通过。

复核 T125 和 T126 的旧清单时分别使用原冻结提交 `27966c5`、`1ba2a0b`。
