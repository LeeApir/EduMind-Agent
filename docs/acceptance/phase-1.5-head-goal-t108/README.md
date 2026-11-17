# T108：限定头插新目标主链接线与准确执行准备

**准备完成，真实调用未授权；T108最终验收尚未完成。** 本次没有真实规划/新模型课程；浏览器证据全部是显式离线夹具，不能填入模型成功分子。准确决策为 [ADR0052 A—D](../../ADR/0052-limited-head-goal-mainline.md)及本包 manifest，需绑定完成准备的本地提交另行批准。旧预算、T106的C2和窗口均不继承。

实际本机开发入口：[http://127.0.0.1:5198](http://127.0.0.1:5198)，API8178，专用测试PG `edumind_catalog_p15_t108_dev`。保留原T107实例5197/8177。此入口仅接收如下准确目标：

> 我已了解 C 指针、struct、NULL 和函数返回值，希望通过头插示例，理解新节点如何连接旧链表，以及为什么调用者需要接收函数返回值。

“我已了解……”是用户自述先备知识，不是测得掌握度，不创建伪造画像。原文完整进入request_1。其他个人字段未知。

## 已接线的路径

```text
现有目标输入 / 原POST API
 → 私有原目标/请求/操作（已有600秒不可变期限）
 → 原规划build_request/Schema/validate_response/persist_outcome
 → 模型选择新示例ID（不是手工大纲） → 原store_plan/outline v1
 → 共享引擎派生代码/事实/轨迹/判空帧 + 新迁移情境/答案
 → 模型完整教学JSON（首稿及至多一措辞修复）
 → 新来源候选审计/原硬身份围栏/原presentation/ready/manifest v2
 → 现有课程组件/私有答案/整组反馈/刷新
```

真实HTTP由本批单前台CLI推进，没有自动worker、第二套调度器或DeepTutor运行框架。现有调度器的预算不是本批授权；本来源操作明确标为finite_head_foreground，budget=null，界面不显示旧13次额度。页面停止阻止课程写入，终端请求需另行Ctrl-C/STOP尽力停止。新建/读取/版本/答题仍使用原私有路由、身份、CSRF、幂等和CAS；新增来源没有公开导入/提交模型JSON的HTTP接口。其他目标、导师/恢复/修订在此开发实例拒绝；生产默认不变。

## 范围与准确共享材料

| 选择 | 初始值 | 依次插入 | 分配掩码 | 独立期望 |
| --- | --- | --- | --- | --- |
| head-new-A | [12] | [4,7] | [true,true] | 最终[7,4,12]，t1→t0→i0→NULL |
| head-new-B | [-8] | [6,0] | [true,true] | 最终[0,6,-8]，t1→t0→i0→NULL |

规划器从两者选择**一个**准确ID，课程只有一场景并包含四种形式，覆盖连接旧链表与接收返回值两目标。真实规划须独立语义核验通过，不手改规划或自动补目标引用。选择失败、澄清、结构或事实问题即停。

复用原引擎 head-insertion-engine-v2 / C模板head-insertion-c-v1。主例有13帧，程序补展示成功NULL判断；初始/caller帧函数局部变量不在作用域。新节点未初始化值明确未知。掩码true允许malloc并假定实际成功；实际malloc失败未演示，模型须解释return旧头。没有任意C执行或释放动画，模型须说明栈/动态生命周期和安全释放次序。

四题使用与主例不同的程序情境：初始[30,40]、插入11，normal与discard_return两版代码。程序从准确轨迹/观察计算链接目标、正常遍历、忽略返回值后的遍历及不可达动态节点数，并用独立闭式结果核对。代码全文由程序提供且题干必须原样引用；模型生成题干/解析。禁止题干给结果或答案格式示例，禁止在课文/逐帧说明代答迁移题；独立语义评估确认，而非用ID存在自证。

## Prompt、Schema与来源

- `planning-system.txt`：现有规划稳定规则＋限定能力规则，Prompt head-goal-plan-v1。
- `planning-schema.json`：原规划输出Schema原样；没有预造真实规划。该完整Schema尚未通过此路由真实验证，协议拒绝即停，不增加探测或逐字段修补。
- `planning-input.template.json` / `planning-request.template.json`：目标/来源/能力/空画像的准确构造示例；UUID位置为明确占位值，不是未来学生或真实请求。
- `teaching-system.txt`、`repair-system.txt`、`teaching-schema.json`：head-goal-course-v1完整正文协议，不使用原固定四观察题契约。
- `head-new-A.materials.json` / B：程序派生准确材料；其选取用显式离线测试规划夹具，**不是模型规划结果**。未来教学输入必须用真实规划构造，不能直接发送测试大纲。
- `candidate-config.json`：本批准确配置和预算。
- 实际构造函数：`scripts/head_course_goal.py:planning_body`、`head_course_materials.content_payload/body`。教学/修复请求取决于尚不存在的真实规划/父稿，不能现在伪造其准确字节；每次真实发送前保存完整实际请求、SHA并冻结父链，任何超限即停，不删字段压缩补发。

程序生成代码、状态、事实、帧、答案、身份和控件；所有前提、课文、逐帧标题/说明、总结、范围/生命周期、四题题干/解析均来自模型原输出，没有缺文兜底。文字字段逐字映射到现有文本插值组件，绝不执行HTML/Markdown/代码。教学实际请求还包含course/operation/request的source_binding，同目标同规划另建课程也不能复用旧候选；原字段/事实引用保留在私有candidate，展示时用同版code_anchor/frame/line绑定；参考答案和解析仅服务端保管，部分作答无解析，完整提交才反馈。

新来源为head_goal_model_generation，public generation_source绑定候选/父稿、真实模型配置、规划摘要、共享材料摘要及evidence_kind。不会借用C01/C02或T107固定身份。私有链：原request → planning_result/plan → selected_example/materials_digest → request/raw body/receipt → candidate/parent → generation_result/validation/presentation → scene_version/manifest → exercise_version/attempt。原稿与唯一修复稿都存档，最终稿入v2；各自结果分别统计。

## 拟议新执行边界

| 项 | 准确值 |
| --- | --- |
| HTTP | 最多3：规划1、完整教学首稿1、有条件普通措辞修复1；单前台，逐步人工启动；没有探测/echo/模型审核/重试/回退 |
| 目标路由 | https://api.deepseek.com/responses，deepseek-flash，reasoning none，temperature0.2，max_output_tokens8000，stream=false，store=false，无工具 |
| 别名 | 固定发送配置，实际回包model严格核对；不声称锁定不可变权重或服务可用性 |
| 本地预约 | 每请求139264输入占额；最多417792；不是可验证token硬界；max_output_tokens合计24000，不能保证上游无隐藏计费 |
| 大小 | 每请求≤131072字节、原body采集≤2097152字节；超限保存前缀并记partial/unknown |
| 时间 | 新登记整数starts_epoch和expires=starts+600；同时受原操作创建后600秒期限约束，取较早截止，不续窗/不重建替代操作 |
| I/O | 90秒单项timeout；DNS同步，无硬总时钟或物理截止保证 |
| 金额 | 无可验证硬上限/实际费率证明，需本批重新接受C2；取消后可能继续计费或迟到账单；旧例外无效 |
| 外发 | 此固定公开目标、自述先备知识、服务器课程/操作/请求UUID、真实规划、新代码/事实/轨迹/答案、当前父稿/定位意见。无画像历史、H、旧私有候选、真实学生作答、其他用户数据或T103助手正文 |
| 审核 | 机械绑定/Schema；独立评估助手核对真实规划、完整首稿与允许修复稿。不占额调用模型审核，不冒称人工正式签核 |

先独立核验规划通过，再生成正文。首稿若仅普通措辞问题，可按`repair-review.json`精确字段path/原文quote/minor difficulty或misconception修复一次；事实、答案、链接、作用域、判空、生命周期、安全、Schema、协议和unknown问题不准修，全批停止。修复返回同Schema完整新稿，父摘要明确；再次独立完整核验。通过后才装配进入本批实际应用。最终仍需实际应用完整学习检查并交独立教学效果评估，不以离线夹具或前置核验代替。

## 可复现入口及未来步骤

零调用：

```sh
backend/.venv/bin/python scripts/run_head_course_goal_dev.py --prepare
backend/.venv/bin/python scripts/run_head_course_goal_dev.py --start
backend/.venv/bin/python scripts/head_course_goal.py --inspect
backend/.venv/bin/python scripts/prepare_head_course_goal_package.py --check
backend/.venv/bin/python scripts/run_head_course_goal_dev.py --test
backend/.venv/bin/python scripts/run_head_course_goal_dev.py --check-migration
```

`--start`已有端口则拒绝，不自动杀服务。测试PG和浏览器的进程权限须按本机工具实际要求放行，不读取.env。测试见[CHECKS.md](CHECKS.md)。

未来准确批准后（**当前不执行这些步骤**）：

1. 准备新可信私有目录建议`/Users/apir/.local/share/edumind/head-goal-r01/`，不得复用已存在批次。0700，Fernet新raw.key 0600；不打印key，不复制T106材料。
2. 先在终端准备好隐藏输入，再登记新600秒起止时刻/准确manifestSHA、version=head-goal-course-v1、explicit_user_authorization=true、accept_ADR0052_A_D_and_batch_C2=true。记录true不能自授权限。创建实际目标课程，立即取得当前浏览器实际owner/course/operation身份，运行`--prepare`。本机数据库凭据仅从专用开发环境取，Provider Key不能经环境/聊天传递。
3. 以最小环境（只有PATH、PYTHONPATH、该专用EDUMIND_DATABASE_URL）执行：`backend/.venv/bin/python -I scripts/head_course_goal.py --send plan --vault <新目录> --approval <新目录>/approval.json`。实际Key只接受终端getpass。完整原body先加密/fsync再解析；规划只存真实模型结果，独立评估写plan-review.json（plan_digest、pass、independent_evaluator）后才能下一步。
4. 同入口`--send generate`。独立完整检查准确candidate；pass写final-review.json，普通措辞才写repair-review.json并且至多执行一次`--send repair`后重评。没有有效独立结论、缺件或过期均停止，不自行填pass。
5. 同入口`--publish`重新解密/复算原件、请求和父链；保存两版审计及最终v2，写published.json与STOP。读取实际应用，完成讲解/代码/所有帧/四题错误及正确反馈/刷新身份检查。导出安全交付摘要、保留失败/未运行清单；独立教学评估后交用户，不开展下一批。

首次规划/生成输出及审核等待会消耗这600秒窗口，窗口不足即停止，不改期限补跑。以上命令的实际专用数据库环境保存在`/tmp/edumind-t108/env.json`（0600、仅测试库凭据），勿贴聊天或提交；凭据、raw.key、私有body、学生会话cookie不进Git。开发测试脚本不应对真实目标课程使用`--offline-fixture`。

## 已知停止与证据局限

入口仍受T102检查后暂停/迟发反例影响；不能把单前台、同请求ID或人工监督当作已修复。Ctrl-C或创建STOP并不保证在途取消，网络完成后发现停止/过期也只保留原件并标未知。异常保留ACTIVE/STOP，不清锁续跑。停止后不再人工启动请求，剩余许可失效。页面取消仅围栏入库；它不会给终端发送进程信号。

原件保存的是HTTP body而非完整网络wire；Authorization不保存。非法JSON先保存可解密body；中断/超限只保留已落盘片段，不能称完整。Key回显阻断明文导出但不是通用编码DLP。原件只有本机所有者保管，没有独立抗篡改/抗共同回滚证据；丢body/raw.key或缺任何原件就判evidence_incomplete/unknown。

T107/T106冻结包、原件和失败保持。T102/T038仍blocked；没有跨主题、通用C、正式掌握度、质量稳定率或生产开放结论。最终新课程仍待准确授权后真实生成；本次提交不含Task-Completed。
