# T108 F01/F02 四字段事实修订准备

当前仅准备，真实HTTP0，尚无新修订课程。拟申请**1次全新真实调用、全新600秒窗口及本批C2**，不继承旧预算，不重跑规划或全文生成。契约提案见 [ADR0052补充](../../ADR/0052-four-field-fact-revision.md)。

## 准确输入与请求

父候选为当前恢复版 `7fde0859549aef0e0e64415880ed67e541dbf3f0d302e7eeae6faf76090b0779`。程序每次从固定恢复包重新核验父稿、原始恢复记录、同版materials/basis和准确F01/F02评估，再构造请求，禁止换成旧失败输出或助手改稿。

- [实际Provider请求](request.json)：完整system/user提示词、父候选、同版代码/事实/轨迹/答案及两条评估，非占位示例。
- [四字符串Schema](output.schema.json)、[准确输入](input.json)、[未授权批准模板](approval.template.json)。只返回paragraph_1_text、paragraph_5_text、paragraph_6_text、learning_summary，映射见输入。无任意path，也无全文输出。
- 模型deepseek-flash，Responses `https://api.deepseek.com/responses`，reasoning none、temperature0.2、max_output_tokens4000，stream/store false，无工具/重试/回退。请求最多131072字节，输入预约139264 tokens、响应2MiB、I/O90秒，只有1 HTTP。金额没有可验证硬上限。

## 实际入口及合并

- 请求构造/合并：backend/app/services/head_course_fact_revision.py。
- 单次前台入口：`backend/.venv/bin/python -I scripts/head_course_fact_revision.py --send`。现在不要执行；新批准和窗口登记前 gate 拒绝。
- 只读核包：`backend/.venv/bin/python -I scripts/head_course_fact_revision.py --inspect`。
- 重建检查：`backend/.venv/bin/python scripts/prepare_head_course_fact_revision.py --check`。

获准后创建新的 `/Users/apir/.local/share/edumind/head-goal-fact-r01/`（0700）、raw.key（0600，本地响应加密键）、独立approval.json，登记实际开始时刻及其后600秒；旧目录/STOP不动。不在本次提前创建窗口或真调用批准。以最小干净环境启动，不读项目.env，Provider Key只在getpass隐藏提示输入；不要在shell提示符或聊天输入。

复用原密封collect/decrypt和phase适配；完整HTTP先加密保存再解析。仅接受缺省/final_answer phase；其他字段/重复键等按严格原适配拒绝。本次不用重复字段恢复。合并通过原完整Schema、事实引用、场景代码及帧绑定，程序deep-copy覆盖固定四路径，其他字段保留原值；候选包含准确parent_digest及新摘要。全文重新assemble，页面总结与演示text_alternative从同一个新learning_summary取值。

成功后保存revision.request/attempt/raw.enc/body/output/diff/candidate/assembled/observation并STOP，失败保留failure和ACTIVE/STOP、partial/unknown，绝不第二次发送。Ctrl-C或新目录STOP尽力停止；暂停后迟发、迟到计费及本机抗回滚局限未解除，T102仍blocked。旧包冻结不改，本包核当前源；manifest排除可变task/process/PRD，未来批准登记另存，不修改本包字节。

## 调用后的唯一推进

先交原四字段输出、四处新旧差异、完整重装配课程和绑定，独立评估助手重评整个课程及F01/F02，不能以Schema通过代替语义通过。若事实/协议/安全/未知或独立非pass，保存准确问题并停，不自动追加调用或助手补写。

独立pass后才实现新来源的最小私有准入并进入原课程组件，保留父版/旧作答，再实测正文、替代文本、13步/高亮/控制、四题反馈和刷新。当前只交请求/合并/装配能力；没有真实新候选，未实施或宣称这个新来源的DB/API/页面验收通过。来源差异已在ADR集中提议，批准后作为同一次修订交付范围，不另建播放器/调度器。最终完整合格课程及独立重评前T108保持未完成。

## 最小检查

`PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q backend/tests/test_head_course_fact_revision.py`：11 passed。覆盖准确父稿/两审核/同版输入/简单Schema、仅四处变化与父稿不变、正文/演示替代文本同时重装配、extra/missing/type/empty/换父/改引用拒绝、重复输出键拒绝；实际前台入口MockTransport成功/未知phase拒绝、完整加密原件回读与唯一请求STOP。夹具文本明确标为离线测试，不是新模型正文，不提供教学纠错成功证据。

新服务mypy、变更Python的Ruff、准确包重建/实际入口inspect及工作流/diff检查通过。未运行新真实HTTP、PG或浏览器；当前未改这些行为，不重复其旧回归。批准后真实课程与页面检查必须实际完成，不以这些离线检查替代。

准备过程在增加输出上限及diff留存时曾出现编辑语法错误、误用observation输出token键的单测失败；已改为真实result.usage.output_tokens，原断言保留，最终同11项通过。全部为Mock，无真实调用。
