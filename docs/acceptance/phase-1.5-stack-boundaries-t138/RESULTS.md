# T138 栈正常操作与拒绝边界的多场景准备

**真实 Provider 调用 0 次。** 本次交付程序材料、可编译示例及准确请求构造。测试提纲和教学正文均是本地协议夹具。真实模型提纲、真实课程和应用学习验收留待后续另定批次。

## 目标、场景与练习

目标原文为「追踪正常入栈和出栈，解释栈顶与后进先出；解释满栈为什么拒绝入栈；解释空栈为什么拒绝出栈，以及拒绝后哪些状态保持不变。」

| 场景及目标来源 | 讲解与实际演示 | 本场景练习 |
| --- | --- | --- |
| `normal` · 目标第一分句 | 沿用既有栈函数和成功主例。空栈初始化后执行 `push(3) → push(8) → pop() → push(5)`。五帧强调有效前缀、栈顶、弹出值和 LIFO，拒绝分支在本场景仅提示。 | 使用既有独立练习代码，辨认首次写入的出栈值与末次出栈后的栈顶，检查两者区别。 |
| `rejections` · 目标第二、三分句，依赖 `normal` | 同一容量 3 的栈函数，使用记录返回值并继续运行的调用者。填满后尝试 `push(9)`，随后弹空并再次 `pop()`。九帧中 f4 实际走满栈拒绝，f8 实际走空栈拒绝；两次均显示 `false`、不变的有效元素和计数、原输出值及底层槽位。空栈失败不会产生新出栈值。 | 使用不同的填充数据和被拒值，分别判断满栈后的元素数、空栈返回值、保留的调用者输出，以及两个拒绝触发的守卫。 |

两个场景的代码是同一个固定容量数组栈实现，调用者职责和观察点不同。正常场景只跟踪成功路径。拒绝场景固定使用有效的 `s/out` 指针并初始化输出变量，无效指针只在文字中说明为不支持的前提，固定容量不扩容是实现约定。可运行 C 样例用于离线核对，播放器使用程序生成的状态数据。

## 程序材料与复用

既有 `stack_course_materials.example` 默认只接受成功路径，保留原输出和拒绝语义。新增显式观察模式记录布尔返回值、调用者输出、有效元素、底层槽位、调用行及 guard 行。边界主例和边界练习的 C 调用者可编译运行并打印这组状态。程序组装练习题干、输入约定和私有答案，模型负责各场景正文和解析；本次固定的是这份课程的练习观察点。

| 独立预期 | 程序轨迹与 C 实测 |
| --- | --- |
| 满栈前后 | f3 和 f4 均为逻辑栈 `[3,8,5]`、`count=3`、底层槽位 `[3,8,5]`、`value=-99`。f4 触发第 9 行守卫，返回 `false`。 |
| 空栈前后 | f7 成功弹出 3，逻辑栈为空，底层仍为 `[3,8,5]`。f8 触发第 16 行守卫，返回 `false`，`count=0`、`value=3`、底层不变，f8 无新出栈值。 |
| 不同数据的练习 | 满栈拒绝后计数 3，空栈拒绝返回 0，调用者输出仍为 1。守卫选项 A 与 C 实际条件一致。 |

程序材料摘要 `fde1d650ce5e6267a9cc7b4c97ad66fe2414e7836705ccb02a612c34545eb0d8`。验证比较了主例及练习完整的八行 C 输出、主例逻辑状态和独立硬编码期望，也核对既有正常五帧与 T119 参考值。

## 准确请求构造

- 规划适配器读取现有规划服务的目标、来源、画像快照。基于原规划请求和本地校验，提供共享材料 ID、两个场景职责、三条原目标引文及练习目标。模型仍负责写出实际提纲、场景目的和目标描述。本批支持域要求正常操作在先、拒绝边界在后，第二场景依赖第一场景；错分目标、遗漏或倒置依赖均拒绝。
- 场景适配器读取现有场景服务的版本化输入，复用场景 ID、目标分配和准确依赖。第二场景要求第一场景的实际快照，测试用明确标记的夹具版本验证此接点。请求只开放讲解段落、事实引用和各题解析。程序合并对应代码、轨迹、题目及答案，经过原场景机械校验。拒绝跨场景解析和未绑定依赖。实际生成后的全文语义审核仍需完成。
- 当前输出是现有 Gateway 的 `StructuredRequest`，包含准确消息、Schema 与参数。真实 Provider 路由、线上格式兼容、有限预算与准入接线另行冻结。当前通用持久化服务会重建其默认请求摘要，后续要让新入口的发出请求与持久化核对使用同一适配器。本次未切换默认运行路径。现有播放器的通用栈投影展示状态和返回结果，守卫行定位保留在材料中，逐行同步显示待实际课程验收。

在仓库根目录复现三个请求和材料：

```sh
export PYTHONPATH=backend:.
pack=docs/acceptance/phase-1.5-stack-boundaries-t138
backend/.venv/bin/python -m scripts.stack_multiscene_requests materials > /tmp/stack-boundaries.json
backend/.venv/bin/python -m scripts.stack_multiscene_requests plan "$pack/planning-input.fixture.json"
backend/.venv/bin/python -m scripts.stack_multiscene_requests scene "$pack/normal-input.fixture.json"
backend/.venv/bin/python -m scripts.stack_multiscene_requests scene "$pack/rejections-input.fixture.json"
```

| 夹具预览 | 输出 SHA-256（含末尾 LF） |
| --- | --- |
| [规划输入](planning-input.fixture.json) | `8f4507c1d910c6e1d4b267820d6ae2c805e26044f2b5db5c90feda3ba4f33220` |
| [正常场景输入](normal-input.fixture.json) | `8924e230c6514230928aac6a96cc4c71bd7cde460ee187f2a6e2f770be4a499f` |
| [拒绝场景输入](rejections-input.fixture.json) | `b76cb292a6df64efb49999bfb075eed96c8b6dc8f07a83aa908fde4fecc90b8c` |

`PYTHONPATH=backend:. backend/.venv/bin/pytest -q backend/tests/test_stack_multiscene.py backend/tests/test_stack_course_profile_prompt_v2.py` 共 **5 项通过**。其中使用 Clang 按 C11、`-Wall -Wextra -Werror` 编译并运行两份拒绝样例，定向校验目标与场景、依赖、程序组装及旧请求原字节。Ruff、任务工作流和 Git 差异检查通过。T137 两课与画像对照未通过记录保留。

## T139 有限执行准备

本节继续记录同一课程。真实 Provider 调用 **0 次**。窗口、真实授权和实际课程尚未建立。历史 T137 课程和对照结果保留。

### 请求、审核与版本顺序

| 阶段 | 实际输入与输出 | 审核与准入 |
| --- | --- | --- |
| `plan` | 实际私有请求的原目标、来源及空画像快照，加上 T138 材料 ID、三条目标与两场景的对应关系。使用 `stack-boundaries-plan-v1` 和闭合的 `stack-boundaries-planning-wire-v1`。正常输出的一项 `plans` 和空原因标记映射回既有业务 Schema，原响应保存在本机。 | 独立核对原目标引文、职责、顺序、示例范围和实际依赖。通过后用原规划服务保存计划，用原场景可用性服务提交私有大纲 v1。澄清或校验失败即停。 |
| `normal` | 已审核的 v1 大纲和正常场景材料，无上游场景。使用 `stack-boundaries-scene-v1` / `stack-boundaries-scene-wire-v1`，模型只写带事实 ID 的段落及两题解析。 | 独立核对正常操作五帧、LIFO、两题及引文。通过后准入正常场景，课程 v2。记录场景版本、内容摘要、候选和审核摘要。 |
| `rejections` | 从同一课程 v2 读取已审核正常场景的完整持久化快照，核对 `scene_version_id`、内容摘要和候选摘要。快照含已审核正文、代码、轨迹、题目、私有答案及解析，作为后续生成的上下文；拒绝场景另附同版材料和四题解析 Schema。发送时省去事务租约序号，其余请求字段和快照按原样绑定。 | 审核绑定两个候选。逐段、逐帧、逐题评估两场景整体教学，通过后提交完整私有课程 v3。两场景可以按同一版本读取，正常场景的版本与 v2 一致。 |

程序继续持有代码、状态、事实、题干与参考答案。场景走现有机械清洗、私有答题和播放能力。新增的封闭 API 投影只为双场景标识来源和行号，五帧场景使用操作行，九帧场景的 f4、f8 使用拒绝守卫第 9、16 行。练习代码独立可见，答案在提交前由服务端隔离。审批记录中的通过是本批教学准入，课程仍为未签核私有草稿。

### 准确执行包

[执行清单](execution-manifest.json) SHA-256 为 `7eecb70f8896e4d7faf394def80618c350db7847e9fa1b8e469a144593ec3646`，列出运行文件、材料、三份请求预览及审核项摘要。规划与场景的实际课程 ID、模型规划和获准上游版本在运行时产生。发送和准入使用同一个构造函数重建请求，并对照实际封存字节；夹具摘要只验证请求构造。

零调用复现 T138 三份夹具的本批 HTTP 请求。标准输出是按发送格式序列化的 JSON，实际保管件无尾部换行。

```sh
PYTHONPATH=backend:. backend/.venv/bin/python - <<'PY'
import sys
from scripts import stack_multiscene_trial as trial

stage = "rejections"  # plan / normal / rejections
fixture = "planning" if stage == "plan" else stage
inputs = trial.read(trial.PACK / f"{fixture}-input.fixture.json")
target = inputs if stage == "plan" else inputs["request"]
target["stack_boundaries"] = trial.basis.VERSION
sys.stdout.buffer.write(trial.canonical(trial.body_for(stage, inputs)))
PY
```

- 拟用已验证的 DeepSeek Responses 传输与严格回执检查。请求模型 `deepseek-flash`、温度 `0.2`、`reasoning.effort=none`、`store=false`、`stream=false`。每次最多请求 8000 个输出 token、请求体最多 128 KiB、响应封存最多 2 MiB、HTTP I/O 超时 90 秒。至多三次发送，合计请求的输出上限 24000 token。真实用量按回执记录，未知结果保留未知。
- 拟由 `start` 登记一个 30 分钟窗口，发送和教学准入都在窗口内。授权记录绑定准确清单、批次、隔离库访客、用途和 1 规划／2 正文／0 修订。开发库固定为本机 `127.0.0.1:15437/edumind_catalog_p15_t139`，离线夹具仅使用同名前缀的 `_test` 库。开发应用复用 `scripts.head_course_goal.serve(8198, stack_boundaries=True)`，以 `EDUMIND_PRODUCT_MODE=dynamic` 运行隔离实例，创建访客后将其 UUID 绑定到本批批准；普通新生成、续跑及后台出站在该实例关闭。
- 后续获准后，从仓库根目录以 `PYTHONPATH=backend:.` 运行 `backend/.venv/bin/python -m scripts.stack_multiscene_trial`。命令顺序为 `start APPROVAL.json`，随后对 `plan`、`normal`、`rejections` 分别执行 `send STAGE`、`inspect STAGE`、`review STAGE REVIEW.json`。审核记录必须填写准确候选摘要、审核者、各项结果、结论及依据。凭据只在每次 `send` 的本机隐藏提示输入。
- 在 `~/.local/share/edumind/stack-boundaries-multiscene-v1/` 保留准确请求、发送预约、加密原件（包括有记录的部分响应）、回执、审核及准入结果。任何失败或结果未知即写 STOP，拒绝后续发送和准入，尝试撤销私有操作；没有重试、回退、探测和修订。人工停止使用 `stop`。如果本机异常退出留下 ACTIVE，先保存证据并停止，该标记会挡住新发送及准入。
- C2 仍待本批接受。费用实账和可验证硬上限未知，停止或超时后已经发出的请求仍可能执行或计费。本地原件无独立抗回滚保障；`store=false` 是请求参数和回执要求。无需复用旧批准或余额。

### 已验证与实际学习验收

- 隔离 PostgreSQL 迁移后，后端定向测试 **7 项通过**。使用 MockTransport 及现有禁外网 audit hook，实际走完请求封存、逐关准入、v3 两场景读取和同版刷新。拒绝旧授权、错审核、被改动的封存请求、错上游摘要、越序、过期、重复发送和停止后继续；传输未知保留预约与失败证据。两组共六题以错误和正确答案分别提交，反馈为 0/1，结果仅作用于本课；其他访客读不到，场景响应无私有答案或解析。
- T138 材料／独立 C 预期及旧栈画像请求 **5 项通过**。前端 Vitest **23 项通过**，含同一数据库投影切换两场景、十四帧逐行定位、两拒绝返回值和旧输出、步进、后退、重置、播放和暂停，以及读写位置恢复与练习代码显示。TypeScript、Ruff 与账本检查通过。
- 实际批次准入后，用同一开发访客进入 v3，阅读两场景并前后切换，核对 5＋9 帧、两个守卫、状态不变和出栈值。每组提交一份错误和一份正确作答，检查解析、隔离与无重复提交。刷新应恢复课程版本、选中场景和可读作答记录。刷新后的播放从场景初始帧开始。独立审核原件、实测访问入口、版本、用量和失败均继续写入本记录。离线夹具与组件测试只证明接线，真实教学与实际浏览器验收尚待执行。

复现离线验收时，先对 T139 专用 `_test` 库执行 `alembic upgrade head`，再把 `EDUMIND_DATABASE_URL` 和 `EDUMIND_TEST_DATABASE_URL` 指向该库。以下命令在仓库根目录执行，投影目录仅保留本次离线 API 响应。

```sh
export PYTHONPATH=backend:.
export EDUMIND_T139_PLAYER_PROJECTIONS=/tmp/edumind-t139-player
mkdir -p "$EDUMIND_T139_PLAYER_PROJECTIONS"
backend/.venv/bin/python -c 'import sys, pytest; from scripts.head_course_goal import raw_io_audit; sys.addaudithook(raw_io_audit); sys.exit(pytest.main(sys.argv[1:]))' -q backend/tests/test_stack_multiscene_trial.py
backend/.venv/bin/pytest -q backend/tests/test_stack_multiscene.py backend/tests/test_stack_course_profile_prompt_v2.py
pnpm --dir web exec vitest run tests/course-visualization.spec.ts tests/course-workspace.spec.ts tests/head-course-status.spec.ts
pnpm --dir web typecheck
```

## T140 有限真实批次

北京时间 2026-11-11 23:14:11 登记用户对准备提交 `aef13d5` 及准确清单 `7eecb70f8896e4d7faf394def80618c350db7847e9fa1b8e469a144593ec3646` 的批准，接受该清单列明的本批 C2。独立隔离库迁移与应用访客已验证，普通生成入口返回 409。批准额度为 1 次规划、2 次场景正文、0 次修订，登记时实际 Provider 调用 0，窗口尚未启动。

### 本批停止结果

北京时间窗口为 **2026-11-11 23:14:35 至 23:44:35**。仅发送 `plan`，DeepSeek 返回 HTTP 200。用已封存响应重放响应外层校验和规划 wire Schema，通过后在本地场景约束处触发 `STACK_PLAN_SCOPE`。

| 字段 | 本批要求 | 封存原文 |
| --- | --- | --- |
| `plans[0].shared_example` | 精确 ID `stack-boundaries-multiscene-v1` | 以「固定容量 CAP = 3 的 C 栈，底层数组 slots[3]」开头的整段示例描述。 |
| `plans[0].scenes[*].scene_key` | 依次为 `normal`、`rejections` | 依次为 `scene_normal`、`scene_rejections`。 |
| `plans[0].scenes[1].depends_on` | `["normal"]` | `["scene_normal"]`，与模型自己的键一致，未绑定到本批指定键。 |

三条原目标引文与场景主题分配可以在原件中核对。原件还使用了 `slots`，而 T138 C 代码的字段为 `data[CAP]`，并把 `count` 称为指针，实际为 `size_t` 计数。以上为停止后的只读诊断，原文及本地门禁均保留。机械门禁已阻断本批，未启动独立语义审核。

| 证据 | 结果 |
| --- | --- |
| 请求／用量 | 实际 **1 次规划、0 次正文、0 次修订**。回执输入 **2560**、输出 **1027** token，共 **3587** token，实际账单未知。剩余两次额度随 STOP 失效。 |
| 准确请求 | `plan.request.json`，SHA-256 `e8b84b1d7fb8db3f816188e2a5b27e3e50966114762368419d833e7a68c95797`，与 `plan.attempt.json` 匹配。 |
| 响应原件 | `plan.raw.enc` 可完整解封，明文 8026 字节，SHA-256 `b1a9f0bd8e90d72c2b3eceb88aa259a696cfe794d53283b0716e8c0b64fc7b69`，与 `plan.body.json` 匹配。封存位置为本机私有目录 `~/.local/share/edumind/stack-boundaries-multiscene-v1/`。 |
| 停止与课程 | `plan.failure.json` 和 `STOP` 存在，`ACTIVE` 已清除。使用既有恢复服务将隔离库内唯一操作从 `cancel_requested` 收尾至 `cancelled`。私有 API 读回 HTTP 200、`head=null`；两个场景均无发送预约，未产生课程版本或学习入口，实际浏览器验收未运行。 |

本批结束，T140 记为 blocked。冻结请求、原件与失败证据保留。

## T141 程序固定大纲双场景准备

本轮范围调整为**程序固定大纲＋两场景模型正文**，验证给定教学顺序下的正文、真实上游衔接和完整课程。结果不纳入模型规划能力。T140 仍为 blocked。已核对旧清单、请求和响应原件摘要以及 STOP，旧失败规划未修补、未导入。

[固定大纲](fixed-outline.json)由 T138 三条目标映射生成。材料 ID 继续使用 `stack-boundaries-multiscene-v1`，场景键为 `normal`、`rejections`，后者依赖前者。每条目标引用实际 `request_1` 原文。程序通过现有规划业务校验、`store_plan` 和 `commit_outline` 保存私有大纲 v1，并登记 `fixed_outline` 来源；启动时生成的大纲须和冻结字节一致。

[大纲事实核对](fixed-outline-review.json)只覆盖目标与程序材料。正常五帧核对成功出栈得到 8、随后栈顶变为 5，拒绝九帧核对 `size_t count`、`data[CAP]`、两处提前返回与原状态。f4、f8 各自返回 `false`，调用者的 `value` 分别保留 `-99`、`3`，两帧均无本步出栈值。两道正常练习和四道边界练习沿用程序答案。离线正文和审核夹具仅用于验证接线。

| 准入顺序 | 绑定与验收 |
| --- | --- |
| v1 固定大纲 | 从实际原目标生成，与冻结大纲及事实核对摘要绑定。此时两个场景均无可学正文。 |
| v2 正常场景 | 发送一次 `normal` 正文，独立审核五帧、两题、LIFO 解释及事实引用后准入。 |
| v3 双场景课程 | 从同一课程 v2 读取已审核的正常场景完整私有快照，核对场景版本、内容和候选摘要后发送一次 `rejections`。整课审核覆盖正常场景与拒绝场景衔接、两次拒绝和六题解析。通过后验收 v3 阅读、十四帧高亮、播放、作答反馈、答案隔离和刷新。 |

[新批执行清单](fixed-execution-manifest.json) SHA-256 为 `6b2cbcdd918acf034efdac7569d0b2caad433f5be95c1363406d81118f56676a`。拟使用新 30 分钟窗口，**0 次规划、2 次场景正文、0 次修订**。沿用 DeepSeek Responses `deepseek-flash`、闭合场景 Schema、每次 8000 输出 token 上限和 90 秒 I/O 超时。请求包含同版代码、轨迹、事实及私有练习材料，第二次还包含已审核正常场景的完整快照。预览内的示例 UUID 和正文夹具用于复现字节构造；真实请求的 ID 和上游快照在运行时绑定。

```sh
export PYTHONPATH=backend:.
pack=docs/acceptance/phase-1.5-stack-boundaries-t138
backend/.venv/bin/python -m scripts.stack_multiscene_trial --fixed-outline preview normal "$pack/fixed-normal-input.fixture.json"
backend/.venv/bin/python -m scripts.stack_multiscene_trial --fixed-outline preview rejections "$pack/fixed-rejections-input.fixture.json"
```

获准后仍用上述模块及 `--fixed-outline`，依次运行 `start APPROVAL.json`、`send normal`、`inspect normal`、`review normal REVIEW.json`，再对 `rejections` 执行发送、检查和整课审核。实际环境使用专用库 `edumind_catalog_p15_t141`、新私有目录 `~/.local/share/edumind/stack-boundaries-fixed-outline-v1/` 和既有本机隔离服务 `serve(..., stack_boundaries="fixed_outline")`。旧批准和旧余额均不适用。失败或结果未知即封存停止，无重试；本批 C2、实际费用未知和停止后可能继续计费等边界按新清单另获接受。

**定向验证**。固定大纲目标、事实和错大纲拒绝 1 项通过。隔离 PostgreSQL 加禁外网 MockTransport 2 项通过，验证 v1 无正文、无模型规划记录、禁发规划、旧批准拒绝、未审核上游阻断、成功时恰好两次模拟正文且第二次读取真实保存的 v2 快照。同版私有 API 投影为 5＋9 帧与 2＋4 题，来源为 `fixed_outline` 和 `offline_fixture`。从实际隔离投影运行的前端 2 项通过，核对高亮、来源标签、场景切换和刷新；TypeScript、Ruff、任务账本及 Git 检查通过。三份旧请求预览摘要也仍与旧清单一致。

本准备任务实际 Provider 调用 **0 次**，新真实窗口和原件目录尚未建立。真实正文、独立教学审核及浏览器学习验收留待本批授权后执行，结果继续写入本记录。

## T142 固定大纲有限真实批次

北京时间 2026-11-11 23:38:03 登记用户对准备提交 `da8f840` 及清单 `6b2cbcdd918acf034efdac7569d0b2caad433f5be95c1363406d81118f56676a` 的批准，接受清单中的本批 C2。授权为 0 次规划、2 次场景正文、0 次修订。登记时 Provider 调用 0，窗口尚未启动。

### 真实执行与停止

北京时间窗口为 **2026-11-11 23:38:36 至 2026-11-12 00:08:36**。程序按准确材料生成并保存大纲 v1，来源为 `fixed_outline`，其数据库计划摘要为 `7c4ed568a1727b11a1557879aa4f366724a0ddf6ad510f1897db4a2d5b3e6690`。仅发送 `normal`，DeepSeek 返回 HTTP 200。机械校验及原件重放通过，候选摘要为 `498dd784b9d854e074ba958685aee1ce358a425b825f135d73f9e59443e2ddd2`。

独立审核助手确认 `normal_five_frames`、`lifo_explanation` 和正文 `fact_support` 通过。五帧为 `[] → [3] → [3,8] → [3] → [3,5]`，演示出栈值 8。两题都要求按 `practice-code` 作答，模型解析引用了演示代码，`two_exercises` 未通过。

| 练习 | 模型原解析的结论 | 独立参考与程序答案 |
| --- | --- | --- |
| `first_pop` | 「第一次 pop 时栈为 [3,8]」并答写入 `8`。 | 练习首次出栈前为 `[-4,6,2]`，写入 `2`。 |
| `final_top` | 「本场景最后一次操作是 push(5)」并答栈顶 `5`。 | 练习依次弹出 `2、9、6`，最后剩 `[-4]`，栈顶为 `-4`。 |

审核还给出一项非阻断意见，将「新元素总被放在」限定为「成功入栈时」。练习预期与 [T119 独立参考](../phase-1.5-stack-lifo-t119/independent-reference.json) 一致。

| 证据 | 结果 |
| --- | --- |
| 实际请求与用量 | **0 次规划、1 次正常场景正文、0 次拒绝场景、0 次修订**。输入 **2760**、输出 **539** token，共 **3299** token，实际账单未知。 |
| 请求与原件 | `normal.request.json` SHA-256 `920fac197bf31bc6fcac111be7499c1e7ead02a8d15b94ff4e63b3a96587a16d` 与出站预约一致。`normal.raw.enc` 解封后 3705 字节，SHA-256 `fcb6992cd4232df5526bec33337b8b61b06e2fa66539e5b14077bb33a16ecefe` 与回执一致。 |
| 审核与失败 | `normal.review.json` SHA-256 `ee186d9f25f9a14e1869364f1b41ab3afa029ed38257026d32daa9934cd1a6a5`，已绑定准确候选。准入拒绝 `STACK_REVIEW_REQUIRED`，保留 `normal.failure.json` 和 STOP；本机私有目录 `~/.local/share/edumind/stack-boundaries-fixed-outline-v1/` 保留原件。 |
| 实际应用 | 专用库中操作已收尾为 `cancelled`。私有课程 API 返回 HTTP 200，当前版本为大纲 v1，两个场景均未准入。整课审核、十四帧和六题的实际浏览器验收未运行。 |

T142 记为 blocked。本批结束，未用的一次正文额度随 STOP 失效。T140 旧失败和 STOP 保留。

## T143 逐题练习证据版准备

T142 的请求、响应、审核、失败和 STOP 已核对并保留。新批次继续使用同一程序固定大纲、演示轨迹、练习代码、题干和答案。每道练习从该题代码的现有程序轨迹提取检查时点、前后状态和参考答案。

| 场景与题键 | 练习检查时点 | 独立预期 |
| --- | --- | --- |
| `normal.first_pop` | 调用行 27，f3 → f4 | `[-4,6,2]` → `[-4,6]`，首次出栈写入 `2`。调用前 `value` 尚未初始化。 |
| `normal.final_top` | 调用行 30，f6 → f7 | `[-4,6]` → `[-4]`，本次弹出 6，当前栈顶为 `-4`。 |
| `rejections.full_count` | 调用行 31，f3 → f4 | 满栈拒绝 `push(7)`，有效元素仍为 `[1,2,4]`，计数为 `3`。 |
| `rejections.empty_return` | 调用行 39，f7 → f8 | 空栈拒绝，布尔返回 `false`，按题意填 `0`。 |
| `rejections.empty_output` | 调用行 39，f7 → f8 | f7 成功出栈写入 `1`，f8 保留旧输出 `1`，本步无新出栈值。 |
| `rejections.guard_pair` | 两次检查，分别对应守卫行 9、16 | `push` 由 `count == CAP` 拒绝，`pop` 由 `count == 0` 拒绝，选 `A`。 |

两份练习代码的 SHA-256 分别为 `fa5fa8572b522b0d75b5f4e2a463ab650bd1a1999fce5e42923537181db5b76d`、`18eb5919901d268eed773ac68b26e9c0446112fdb70fa256e2b7470bfefa4959`。正常练习逐帧对照 [T119 独立参考](../phase-1.5-stack-lifo-t119/independent-reference.json)；拒绝练习沿用 T138 的独立预期及实际 C 输出。证据中的检查点 ID 属于特定题键，即使两题观察同一次调用也分别绑定。

- 发送正文时，`demonstration` 提供本场景的演示代码、帧和 `demo.<场景>.*` 事实。每个练习在 `practice.questions` 提供自己的 `practice.<场景>.<题键>` 证据、代码摘要、检查点和答案。模型返回自然语言解析、该题证据 ID 和有序时点 ID。程序集成解析原文，练习代码与参考答案仍由程序装配。
- 拒绝场景从已审核正常场景的真实持久化快照读取上游。实际请求只带其场景版本、摘要和标为衔接背景的教学段落；上游练习、解析和事实表留在本机快照。拒绝场景的正文和练习各自引用本场景材料。
- 机械校验用冻结的材料和原请求重建绑定，并核对证据 ID、代码版本和时点。独立审核逐题阅读解析，核对它是否从所列状态和准确代码推出答案，再复查整课衔接。正常场景的 `first_pop_explanation` 和 `final_top_explanation` 都须通过才保存 v2 并允许发送拒绝场景。第二场景审核逐项覆盖四题，同时核对正常与拒绝场景的衔接。沿用同一审核和准入流程。

[新版准确执行清单](evidence-execution-manifest.json) SHA-256 为 `4ab260912e0a064278465b45a0e7f5c5536e1e164d20c1f1bbc67a7b728867cd`。提示词 `stack-boundaries-scene-evidence-v2`，输出 `stack-boundaries-scene-wire-v2`，证据 `stack-practice-checkpoints-v1`。新材料摘要同时覆盖原程序材料与逐题证据。下列离线请求预览带有明确的夹具身份，实际发送使用专用访客的请求与真实上游。

```sh
export PYTHONPATH=backend:.
pack=docs/acceptance/phase-1.5-stack-boundaries-t138
backend/.venv/bin/python -m scripts.stack_multiscene_trial --practice-evidence preview normal "$pack/evidence-normal-input.fixture.json"
backend/.venv/bin/python -m scripts.stack_multiscene_trial --practice-evidence preview rejections "$pack/evidence-rejections-input.fixture.json"
```

拟议 **30 分钟、0 次规划、2 次场景正文、0 次修订**，沿用 DeepSeek Responses `deepseek-flash`、90 秒 I/O、每次最多 8000 输出 token 和既有 C2 条件。实际费用未知，失败或结果未知即封存停止。新批授权后使用 `--practice-evidence` 的同一入口，按 `start`、正常场景 `send / inspect / review`、拒绝场景 `send / inspect / review` 执行。新隔离库为 `edumind_catalog_p15_t143`，新封存目录为 `~/.local/share/edumind/stack-boundaries-practice-evidence-v1/`；私有隔离应用沿用 `serve(..., stack_boundaries="practice_evidence")`。新窗口和预算须另行批准。

定向检查通过 3 项轨迹与装配、2 项禁外网 MockTransport 与隔离库检查。反例覆盖演示材料冒充练习、跨题和跨场景 ID、错时点、错练习代码，以及正确绑定却从演示得出错误解析时由独立审核拒绝准入。隔离库核对第二次请求精确绑定已保存上游、私有投影保持 5＋9 帧和 2＋4 题，答前无答案和解析。旧两批请求预览摘要仍匹配各自清单。准备阶段实际 Provider 调用 **0 次**。

## T144 逐题证据有限真实批次

北京时间 2026-11-12 08:55:50 登记用户对准备提交 `4f6a56f` 及准确清单 `4ab260912e0a064278465b45a0e7f5c5536e1e164d20c1f1bbc67a7b728867cd` 的批准，接受本批 C2。额度为 0 次规划、2 次场景正文、0 次修订。登记时实际 Provider 0，窗口尚未启动。

### 真实执行与独立审核

北京时间窗口为 **2026-11-12 09:00:45 至 09:30:45**。程序固定大纲 v1 的数据库计划摘要为 `a99ef33372ec2ae68d7886ced4a1b2be6f31d5781595ecb94dab12513b9d2d7b`。两次正文均返回 HTTP 200，通过严格响应校验、原件重放和逐题证据绑定。

| 场景 | 候选摘要 | 独立审核与准入 |
| --- | --- | --- |
| 正常 | `8de4b6f5cd167dc406c3e710437a09a49fde4e9e66c1cdfdc9743f8843ce1d07` | 六项通过，保存 v2。五帧与 LIFO 说明正确。练习行 27 首次出栈写入 `2`，行 30 最后弹出 6 后剩 `[-4]`，栈顶 `-4`。 |
| 拒绝及整课 | `6410b7734ffa9cf3c6acfd4110bbd3227c07d13dafed3f1fe8757355af42c0e0` | 十一项通过，保存 v3。四道解析分别从专属练习时点推出 `3`、`0`、`1`、`A`，并区分失败时的旧输出和本次出栈值。 |

第二次发送发生在正常 v2 审核和保存之后。拒绝场景实际请求的 `upstream_context` 绑定正常场景版本 `2cd06cde-9c3f-4f62-af5f-eb8439a7c8f7`、场景内容摘要 `5a7c14f68ace0f89f1435133ccd764169d9070336c06df39169afdc1ad00171c` 和该版正文衔接背景。两次拒绝分别高亮守卫行 9 与 16，均返回 `false`，保持逻辑栈、底层槽和输出。拒绝演示 f8 的旧输出为 3，拒绝练习 f8 的旧输出为 1，均无本次出栈值。

独立审核的非阻断意见包括将正常正文中的快照术语 `top 为 null` 写成「没有栈顶」，将「守卫通过」写成「没有触发拒绝」。拒绝 f0 表示初始化完成后的快照，高亮定位到 `s` 初始化行 23，`value=-99` 位于紧接的第 24 行。验收保留模型原文。

### 实际私有应用验收

本机 [开发应用](http://127.0.0.1:5220/) 的私有课程为 `b441ebc0-5d53-4f8c-9188-783d609c5e9b`，完整版本 v3。运行 `sh /tmp/edumind-t144/open.sh` 可用本批访客身份打开。API 读回操作为 `succeeded`，两场景均可读取。

在 Chromium 中读完两场景，逐步核对 **5＋9 帧**、代码行高亮、播放、暂停、上一步和重置。两组 **2＋4 题**各提交一次全错和全对作答，匹配比例为 0% 和 100%，每题反馈与准入原文一致，结果仅作用于本课。刷新保留 v3、所选场景、已填答案及反馈，未重发作答。切回正常场景仍能读取该组反馈。答前场景响应无参考答案键和解析，另一访客无法读取两场景或作答记录。四次学习提交均为本地验收，无页面错误。[浏览器证据](t144-browser-results.json)

### 用量与原件

实际 **0 次规划、2 次场景正文、0 次修订**。正常场景回执输入 3505、输出 780 token，拒绝场景输入 6707、输出 1270 token。合计输入 **10212**、输出 **2050**，共 **12262** token，实际账单未知。

| 场景 | 请求 SHA-256 | 响应原文 SHA-256 | 审核 SHA-256 |
| --- | --- | --- | --- |
| 正常 | `4cf04cf795a37dee0a94dc872b961a72c19f43c68b3c7e5bc47f679861b78aca` | `7ca6c854dbe47a3408d915ea4fd102d82121e473f48823c2f3293425baae70f0` | `c5215d4ea5c7c2fa3b1233b079b7a494fc2c3a660edc81b95066c15c73bc0c54` |
| 拒绝 | `846f8f14c37463a1be875e4c590fff4f7778343915b2806cbb136c29fe5ced5b` | `0552c159da037692ada9e37d3de1c2894755baf045b15d0118c1c2f893c3b7aa` | `20f280539a4eac5c1ddafd3052e7b0eb13221a4ad9c6001b689e391abc58f4ed` |

原件、预约、回执、审核与准入记录封存在 `~/.local/share/edumind/stack-boundaries-practice-evidence-v1/`。本批已写 STOP 结束，T142 的失败原件及 STOP 保留。

## T145 最小目标选择准备

T144 保留为已验收的固定双场景基线。新适配只增加目标选择，继续使用 T144 的材料 ID、代码、轨迹、逐题证据、私有答案和审核准入。准备阶段实际 Provider 调用 **0 次**。

| 用户目标 | 选择及课程结果 |
| --- | --- |
| 理解栈操作和 LIFO | `operations`，程序只装配正常场景，5 帧、2 题。 |
| 理解正常操作及满栈、空栈拒绝 | `operations_and_rejections`，程序依次装配正常、拒绝两场景，14 帧、6 题。拒绝场景依赖准入后的正常场景。 |
| 请求动态扩容等超出这两个教学单元的内容 | `out_of_scope`，保留原文引证，用现有澄清状态报告范围，计划为空。混合目标中的未支持要求也按此处理。 |

模型响应只有 `selection` 和 `evidence`，证据项只有类型、来源键及原文片段。请求只提供原目标、来源文本和选择规则。程序持有材料 ID、场景键、依赖、代码及实现描述，选择协议不接受这些字段。输入可用同义和否定表达；原文子串检查用于核对引用真实性。

新适配复用规划服务的请求快照、Provider-neutral 请求类型、摘要、业务 Schema、持久化和澄清状态。原始选择响应留在规划审计记录，程序据选择和引文生成正式计划，大纲准入时重验。课程来源标为 `goal_selected`，使用与 T144 相同的逐题材料摘要。两场景沿用已有依赖读取和准入接口。正常单场景的正文请求明确限定已选场景。

[六份准确请求与预期夹具](t145-goal-selection-requests.json) SHA-256 为 `90465ed27d6bb8c1ebfe86d08f7621016bd4c23a459fa302aae653f16389f0b4`。每例含完整 system/user 消息、封闭 JSON Schema、请求参数和现有规划摘要。提示词版本为 `stack-goal-selector-v1`，响应版本为 `stack-goal-selector-response-v1`。文件中的预期响应为离线夹具。

定向检查 **10 项通过**。六个目标覆盖两种正例及其同义表达、明确不要求扩容、混合扩容要求和「容量翻倍」表述。反例拒绝伪造引文、漏项、重复依据、自定义材料或场景字段，以及被改写的依赖。三个隔离库用例核对原始响应保留、单场景 v2、双场景 v3、第二场景上游绑定，以及范围外仅返回澄清、无课程版本。TypeScript、Ruff、账本检查通过，旧三批请求预览摘要仍匹配各自清单。

同义测试验证同义输入的接线和引文保留。真实模型是否正确理解同义、否定和混合范围，须在后续真实批次独立复核后再准入，并继续按 T144 的逐题与整课标准验收。真实路由、预算和执行窗口另定。T038 状态及旧失败记录保留。

## T146 三目标真实执行清单

用户确认三个样本和最多 **6 次请求**，含 **3 次目标选择、3 次场景正文、0 次修订**。本任务冻结执行包，实际 Provider 调用 **0 次**。真实窗口与专用访客在获本清单执行授权后创建。

| 样本 | 固定输入 | 预期及验收 |
| --- | --- | --- |
| A | 想懂压栈、弹栈和后来压进去的先出来，不用讲动态扩容。 | `operations`，独立核对否定约束和 LIFO 引证。完成正常场景 v2，5 帧、2 题。 |
| B | 先学压入弹出，再看塞满时压不进、一个也没有时弹不出的原因。 | `operations_and_rejections`，独立核对三类目标和同义表达。完成双场景 v3，14 帧、6 题。 |
| C | 理解栈操作和动态扩容 | `out_of_scope`，证据应指向扩容要求。既有澄清状态报告范围，无课程版本、无正文。 |

发送顺序为 A 选择 → B 选择 → C 选择 → A 正常 → B 正常 → B 拒绝。每一步先封存与严格校验，再独立审核后准入。选择审核检查语义、逐字原文引用和范围完整性；三项通过后才发送正文。B 正常两题解析均通过并保存后，拒绝场景才读取其准确版本、摘要和衔接段落。A、B 沿用 T144 的逐题、逐帧和整课审核，实际浏览器验收覆盖阅读、高亮、播放控制、每题反馈、答案隔离及刷新。C 只读回范围提示和无版本状态。

[准确执行清单](selection-execution-manifest.json) SHA-256 为 `b4c58582b17dc7f8d0e034e20930d8a5bfdf85bd1a18d8b6eba49b537c76aee6`。包含三次选择的内部请求摘要及准确 HTTP 请求体摘要，均从 T145 原样构造。三次正文的实际请求取决于审核后的计划引证、私有版本和 B 的真实上游；程序文件、材料摘要和响应契约在本清单冻结。每份实际请求和响应按步封存。

```sh
export PYTHONPATH=backend:.
backend/.venv/bin/python -m scripts.stack_goal_selection_trial preview A
backend/.venv/bin/python -m scripts.stack_goal_selection_trial preview B
backend/.venv/bin/python -m scripts.stack_goal_selection_trial preview C
```

拟沿用 DeepSeek Responses `deepseek-flash`，**全批 30 分钟**、每次 90 秒 I/O、最多 8000 输出 token。仅在隐藏提示中输入密钥。获清单执行授权后，以同一模块的 `start APPROVAL.json` 建立窗口和三个独立访客的课程操作，再按清单逐步执行 `send SLOT STAGE`、`inspect SLOT STAGE`、`review SLOT STAGE REVIEW.json`。选择步骤名为 `plan`，正文为 `normal` 或 `rejections`。开发库为 `edumind_catalog_p15_t146`，应用复用 `serve(..., stack_boundaries="goal_selection")`，新封存目录为 `~/.local/share/edumind/stack-goal-selection-v1/`。

选择错误、审核失败、网络结果未知或窗口不足时，保留原件及预约并停止整批。无重试、回退或追加调用。实际账单未知，既有 C2 费用和在途请求边界随本清单提交执行授权。T144 基线、旧失败和 T038 状态保留。

隔离 PostgreSQL 与禁外网 MockTransport **4 项通过**，覆盖全六步、错单元、审核失败和超时未知。验证未审核完三项时不能发送正文、C 无正文权限、B 绑定实际保存的上游、成功后 A v2 和 B v3 均完整、C 无版本。栈材料与装配 **5 项通过**，旧三批请求预览摘要一致。真实执行及浏览器验收尚未开始。

## T147 三目标真实批次

北京时间 2026-11-12 09:49:24 登记用户对准备提交 `6b40312` 及本批 C2 的批准。准确清单 SHA-256 为 `b4c58582b17dc7f8d0e034e20930d8a5bfdf85bd1a18d8b6eba49b537c76aee6`。额度为 3 次目标选择、3 次场景正文、0 次修订，整批 30 分钟。实际账单未知，没有可验证费用硬上限，停止后仍可能计费，本机原件没有独立抗回滚保障。登记时实际 Provider 调用 0 次，窗口尚未启动。

已在专用数据库 `edumind_catalog_p15_t146` 建立三位独立访客。开发应用和后端仅监听本机，三位访客的普通课程生成入口均返回 409。

实际整批窗口为北京时间 **2026-11-12 09:52:56 至 10:22:56**。A 选择已封存，实际 HTTP 200，实际请求摘要与冻结清单一致。

### 选择与审核结果

| 样本 | 模型选择及原文依据 | 独立审核与私有准入 |
| --- | --- | --- |
| A | `operations`，`normal` 引用「想懂压栈、弹栈和后来压进去的先出来」 | 三项独立审核通过。「不用讲动态扩容」是明确排除项。保存 v1 单场景大纲。候选 `8e809d89df000249d7f9771305fba9f9368a88a2b775f2a4cdf15c36a50a10df`。 |
| B | `operations_and_rejections`，分别引用「先学压入弹出」「塞满时压不进」「一个也没有时弹不出」 | 三项独立审核通过。保存 v1 双场景大纲。候选 `75bb0df22b92e874e939d227665cfc4aa987a6ada8ee8c55ec64de73d2c56f2f`。 |
| C | `out_of_scope`，`normal` 引用「理解栈操作」，`unsupported` 引用「动态扩容」 | 选择值符合预期，两条引文均可在原目标找到。该选择要求证据类型集合严格等于 `{unsupported}`，额外的 `normal` 触发 `STACK_SELECTION_EVIDENCE`。本地拒绝，未形成合格候选，未审核或准入澄清。 |

C 的原件返回 HTTP 200 和 `completed`。以冻结请求和未修改的原始正文离线重放，复现同一错误。校验触发点为 [选择证据集合校验](../../../backend/app/services/stack_goal_selection.py#L97)。失败属于证据集合约定，语义上模型确实识别到动态扩容超出范围。

### 用量与原件

| 样本 | 输入 token | 缓存命中输入 token | 输出 token | 请求 SHA-256 | 响应 SHA-256 | 审核 SHA-256 |
| --- | ---: | ---: | ---: | --- | --- | --- |
| A | 512 | 0 | 39 | `f57790fd191b1521bcb7bc8418ab09669a6912e73f0a05f125efddaaeef540fb` | `e1628da2e45ef0d351b03a7201378bfa1042c47645ca656758906f8d4ac2f609` | `7187046cac41b83394ea3e10878b3aa0e2590c3e84db38597230118c52712d69` |
| B | 516 | 256 | 81 | `1c9dda6e1039d7a76335786b00edc286b22dc6ab2f7c55558a8a4e5c436a0e94` | `cf3106f8f90a2168ece957baf59b2314231bdfbdc08b5fb302d20343e8016c50` | `6c9faf205f24b7d2b0c23af40396935e0856851997261c72eada7cda1e46ebdc` |
| C | 486 | 256 | 52 | `c81f9273069f2594c141071d6c2fe2a571e3e0a5a5e76edbfe5ffd44954bb2d8` | `97bd062d11c4dbedc7ae529d5cbf9da764ea61cd052b6569f70943f313ac2eed` | 未到审核 |

实际 **3 次选择、0 次正文、0 次修订**。回执合计输入 **1514**、输出 **172**，共 **1686** token。缓存命中输入为 512 token，包含在输入合计中。实际账单未知。三份实际请求摘要均与清单一致，响应解密摘要均与封存回执一致。

封存目录为 `~/.local/share/edumind/stack-goal-selection-v1/`。各样本子目录保留 `plan.request.json`、`plan.raw.enc`、预约及回执。A/B 同时保留候选、审核与准入记录，C 保留 `plan.failure.json`。批次 STOP 已落盘，后续正文入口在读取密钥前返回 `STACK_BATCH_STOPPED`。

### 私有应用终态

| 样本 | 私有课程 ID | 操作 ID | API 读回 |
| --- | --- | --- | --- |
| A | `c4fc7fc6-19fd-466c-8d7b-1ce7c31957b0` | `f904a86f-ea92-4fae-a12b-2011e142357f` | `cancelled`，v1 单场景大纲，0 个就绪场景。 |
| B | `89cad7f4-2c1b-4b9a-af13-589490cde19d` | `4ff41b38-1b3f-490f-8607-4f139f8ac23b` | `cancelled`，v1 双场景大纲，0 个就绪场景。 |
| C | `2178b88e-f9be-4209-b873-6f740bc519e8` | `c87de318-0d3a-46e6-98f9-628a0547ae0d` | `cancelled`，无课程版本、无已准入的范围提示。 |

本机执行 `sh /tmp/edumind-t147/run.sh inspect A plan`、`inspect B plan` 后按独立审核准入。C 失败后，用只读原件重放核对失败，再运行 `PYTHONPATH=backend:. backend/.venv/bin/python /tmp/edumind-t147/finish-stop.py`，既有收尾服务处理了 3 个取消操作。通过 `backend/.venv/bin/python /tmp/edumind-t147/check-status.py` 读回上表。正文未发送，浏览器学习验收未执行。T147 保持 blocked，剩余三次正文额度随 STOP 失效。T144 固定双场景课程保留，T038 保持 blocked。

## T148 新版范围外证据与 A/B 续接包

`stack-goal-evidence-v2` 要求 `out_of_scope` 提供一条准确支持正向范围外要求的 `unsupported` 引文。可同时保留 `normal`、`full_push`、`empty_pop` 的有效正向引文，每类最多一条。程序核对来源键、逐字子串和重复，独立审核逐条核对完整原句的语义、否定和范围覆盖。未通过审核或审核与原件摘要错配时拒绝。只要存在正向范围外要求，审核通过的结果也只有范围提示，`plan=null`、`body_allowed=false`。

C 的封存响应在新版中保留原顺序和两条引文。独立审核确认「理解」统摄「栈操作」和「动态扩容」两项正向要求。前者支持 `normal`，后者支持 `unsupported`，两条均来自 `request_1`。新版结果为「当前课程支持固定容量栈的正常操作和满栈、空栈拒绝。该目标超出支持范围。是否改为学习这些内容？」本步为离线派生诊断，未写入应用。[原件绑定及独立审核](t148-scope-replay.json)

旧 T147 的 C 仍为 `STACK_SELECTION_EVIDENCE`。原请求、响应、失败、STOP、取消状态和失效额度保留。新规则及新批准备均实际调用 **0 次**，新版选择请求构造没有发送入口。

### A/B 续接与执行边界

隔离检查从 T147 读回 A/B 原始规划审计、已审候选及 v1 大纲，核对其与封存请求、响应、审核和准入摘要一致。新批为两个新访客创建新的课程、请求、操作和大纲版本。程序从各自已审核选择重新装配同一大纲内容，再用新快照绑定正文请求。新操作的策略快照和准入记录保存 `reviewed_selection_replay`、旧操作 ID 及原件和审核摘要。旧大纲无改动，新操作无选择调用记录。C 无续接操作。

拟用 DeepSeek Responses `deepseek-flash`，整批新窗口 **30 分钟，0 次目标选择、3 次正文、0 次修订**。顺序为 **A 正常 → B 正常 → B 拒绝**。B 拒绝须读取本批 B 正常已审核并保存的版本及摘要。使用既有场景提示词、Schema、逐题证据和独立审核门槛。请求须待私有版本及 B 上游快照产生后构造，发送前封存实际字节。每请求最多 8,000 输出 token，I/O 限 90 秒，正文大小界线见清单。实际账单未知，无可验证费用硬上限，停止后仍可能计费，本机原件无独立抗回滚保障。

先单独批准准确清单及新 C2 风险，再使用两个新访客及新批准文件启动。窗口内逐步执行，模型只负责正文。任何失败、结果未知或窗口不足时封存并停止，额度不结转，重试与回退均为零。通过后验收 A v2（5 帧、2 题）和 B v3（14 帧、6 题）的阅读、演示、高亮、播放、反馈、答案隔离及刷新。新批原件目录为 `~/.local/share/edumind/stack-goal-continuation-v1/`。[准确执行清单](selection-continuation-manifest.json)

```sh
export PYTHONPATH=backend:.
backend/.venv/bin/python -m scripts.stack_goal_continuation parents
backend/.venv/bin/python -m scripts.stack_goal_continuation replay-c REVIEW.json
backend/.venv/bin/python -m scripts.stack_goal_continuation start APPROVAL.json
backend/.venv/bin/python -m scripts.stack_goal_continuation send A normal
backend/.venv/bin/python -m scripts.stack_goal_continuation inspect A normal
backend/.venv/bin/python -m scripts.stack_goal_continuation review A normal REVIEW.json
```

前两条为只读原件核对。后续命令须在新授权下运行。新批准文件由 `approval_values` 绑定准确清单、两位新访客和额度，运行环境使用现有本机专用库 `edumind_catalog_p15_t146`。发送仍只在本机终端隐藏提示输入密钥。

### 定向验证

- `PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.stack_goal_continuation replay-c REVIEW.json` 重新解密并核对 C 的封存摘要，逐项通过独立审核，得到原样两条引文和仅范围提示的结果。审核取自上方派生记录。
- `backend/.venv/bin/python -m pytest -q backend/tests/test_stack_goal_evidence.py backend/tests/test_stack_goal_selection_trial.py --tb=short` 在 `EDUMIND_T148_ARCHIVE_CHECK=1`、专用 PostgreSQL 和禁外网审计钩子下执行，**14 项通过**。覆盖伪造、重复、否定语义审核失败、错审核绑定、旧批准拒绝、跨槽大纲换绑、C 和规划无发送权限、乱序及停止拒绝。实际 A/B 旧原件经只读核验，新测试操作以 MockTransport 完成 A v2 和 B v3。
- Ruff、工作流账本、`git diff --check` 及旧清单 SHA-256 检查通过。真实窗口和浏览器学习尚未启动。

## T149 A/B 续接真实正文

北京时间 2026-11-12 14:12:41 登记用户对准备提交 `4132f9b` 和本批 C2 的批准。准确清单 SHA-256 为 `e94374813efb3f4f1c05883469a5d153bcc7ffd73d1e6c369e01d65b6618cbb8`。额度为 0 次选择、3 次正文、0 次修订，整批 30 分钟。实际账单未知，无可验证费用硬上限，停止后仍可能计费，本机原件无独立抗回滚保障。登记时 Provider 0 次，窗口未启动。

复用本机隔离开发应用，创建两位新访客并核对会话身份。新访客访问各自 T147 来源课程均返回 404，普通生成入口返回 409。T147 STOP 与已审选择原件通过完整摘要核验。

实际整批窗口为北京时间 **2026-11-12 14:13:03 至 14:43:03**。A、B 已保存各自新大纲 v1，并分别绑定原 T147 审核。A 正常场景已封存，HTTP 200。

A 正常候选 `0d97ff826244d3910936af8f475c4dd73dd89e5ca085e9411766893b9403c82a` 六项独立审核通过。五帧与演示 C 行 22、24、25、26、27 对齐。两题按各自代码和快照推出首次弹出 2，以及末次弹出 6 后栈顶为 -4。非阻断意见是将「新的 `data[count]`」表述为「递减 `count` 后读取 `data[count]`」，保留模型原文。

A 私有课程 `74292fc7-a597-45c0-a5d7-035ae2fd421c` 已保存 v2。Chromium 读完四段，核对五帧状态和高亮，以及播放、暂停、前后步和重置。两题分别以一组全错和一组全对作答，服务端匹配率为 0% 和 100%。答前无答案键与解析，其他访客不能读课程或作答结果。刷新恢复同版、已填答案和反馈，未重发作答。[A 浏览器证据](t149-browser-A.json)

### B 认证失败与终态

B 正常场景请求已发送。原始响应为 DeepSeek **HTTP 401**，错误类型 `authentication_error`、错误码 `invalid_request_error`，正文指出所用 API Key 无效。入口要求完整的 HTTP 200 回执，因此返回 `STACK_BODY_RECEIPT` 并写入整批 STOP。加密响应已核对摘要。没有 B 正常候选或审核，B 拒绝场景未发送。

| 样本 | 新私有课程和操作 | 新大纲摘要 | 私有应用读回 |
| --- | --- | --- | --- |
| A | `74292fc7-a597-45c0-a5d7-035ae2fd421c` / `0913bf4b-2693-4022-aaa9-9af63c5b50d9` | `1d0970a4005c481ddd7f7b041c30d98388bd8dc4bc0d2a84aa902f660bc62dff` | `succeeded`，完整 v2，五帧及两题。 |
| B | `9437333d-2a2c-4ba2-86d7-a9318e8e85cf` / `eeb03ebe-8dd7-4cc2-9896-1eedfda5aad3` | `7d19cec62870ed367d31bb1e56785ce4351eab6f50f07c438a5dfe80bd72c783` | `cancelled`，v1 双场景大纲，0 个就绪场景。 |

A、B 新操作分别保留 T147 已审选择及原件摘要。使用既有收尾服务处理 B 的取消，STOP 后仍可读回 A v2 及两组练习反馈。后续正文入口在读取密钥前返回 `STACK_BATCH_STOPPED`。A 可通过本机 [开发应用](http://127.0.0.1:5222/) 学习，运行 `sh /tmp/edumind-t149/open.sh A` 以该批私有访客身份打开。B 的浏览器学习验收未执行。

### 用量与原件索引

| 场景 | HTTP | 输入 / 输出 token | 请求 SHA-256 | 响应 SHA-256 | 审核 SHA-256 |
| --- | ---: | --- | --- | --- | --- |
| A 正常 | 200 | 3098 / 635 | `bcf0152725ff139c346911da3263a08e6a1abcc8f6c2b684099389c54736aa54` | `d22fec555e44020c2cf0c9752b9252c63b9da109c827880c46855dcf2c99c005` | `88d024d5315d126071f6c341398fafd6e7de2fef898b857dea2d1eab9d4a628f` |
| B 正常 | 401 | 响应未回报 | `34f7efe00bbefd8f2a6427ceadbc400e67346408e0dbc565fabc0c6d7194a153` | `d3434b66aaebac9916f909cff3ba1d432f8b41dc54327ac015f7a1b599623fdd` | 无候选 |

实际 **0 次选择、2 次正文 HTTP、0 次修订**。A 回执报告 3733 token，B 的 401 无用量回执。实际账单未知。请求、加密响应、回执、A 审核与准入及 B 失败记录保存在 `~/.local/share/edumind/stack-goal-continuation-v1/`。

用 `sh /tmp/edumind-t149/run.sh inspect A normal` 核对 A 封存原件，再用绑定的审核文件准入。执行 `PYTHONPATH=backend:. backend/.venv/bin/python /tmp/edumind-t149/check-browser.py A` 完成浏览器验收。B 失败后用 `finish-stop.py` 和 `check-status.py` 核对取消与私有读回。T149 保持 blocked，未使用的第三次请求随 STOP 失效。T147 及 T038 的历史结果保留。

## T150 B 单独重测准备

T149 已 STOP，且准确清单的第一步为 A 正常。B 重测复用 T149 的正文构造、DeepSeek Responses 传输、封存、独立审核及私有准入。新入口仅允许 B 正常和 B 拒绝，重新绑定 T147 已审核 B 选择到新访客和新私有操作。旧 T149 的 B HTTP 401 原件及 STOP 已重验。A v2 可继续学习。准备阶段 Provider 调用 **0 次**。

[准确清单](selection-b-retest-manifest.json) SHA-256 为 `4e511f25a9d38da951b31c170f25e318229a635129c6ab0e5cdad36f7953559c`。拟用同一 DeepSeek `deepseek-flash`、同版提示词、Schema、材料和审核标准，**30 分钟，0 次目标选择、2 次正文、0 次修订或额外探测**。B 正常须独立审核并保存 v2 后才发送拒绝场景，实际请求绑定本批正常场景版本和摘要。新私有 UUID 与上游版本由实际运行产生，发送前封存请求字节。每请求 I/O 限 90 秒、输出上限 8000 token。实际金额未知、无可验证费用硬上限、停止后仍可能计费，本机原件无独立抗回滚保障。

获准确授权后，使用本机隔离库和新批准文件调用 `PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.stack_goal_b_retest start APPROVAL.json`。后续使用同一模块的 `send normal`、`inspect normal`、`review normal REVIEW.json`，再处理 `rejections`。只在本机隐藏提示输入有效 DeepSeek Key。任何响应拒绝、未知、审核未通过或窗口不足均封存并停止，无重试与回退。新原件目录为 `~/.local/share/edumind/stack-goal-b-retest-v1/`。完成后验收同课 v3 的阅读、14 帧及高亮、播放、6 题反馈、答案隔离与刷新。

`PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.stack_goal_b_retest source` 重放已封存 B 请求和失败摘要，并核对原独立审核。专用 PostgreSQL、`EDUMIND_T150_ARCHIVE_CHECK=1` 和禁外网审计钩子下执行 `backend/.venv/bin/python -m pytest -q backend/tests/test_stack_goal_b_retest.py --tb=short`，两项通过。覆盖 B 两正文及本批上游绑定、同版正常请求模板、旧批准拒绝、乱序拒绝、401 停止和旧原件保留。Ruff、工作流和旧清单摘要通过。真实执行另行批准。

## T151 B 双场景真实重测

北京时间 2026-11-12 14:34:48 登记用户批准 `eabf812` 及本批 C2。准确清单 SHA-256 `4e511f25a9d38da951b31c170f25e318229a635129c6ab0e5cdad36f7953559c`。30 分钟内允许 0 次选择、2 次正文、0 次修订。已核对专用访客、旧课程访问隔离及原件绑定，登记时 Provider 0 次。

实际窗口为北京时间 **2026-11-12 14:35:06 至 15:05:06**。新私有操作保存已审 T147 B 选择绑定的大纲 v1。正常场景已收到 HTTP 200，原件重放通过。

正常候选 `7696cf40d0ebfb1b6848366adfc806e2a0ecf5c81c05f23d9d8169b8b8d45577` 六项独立审核通过并保存 v2。五帧展示空栈、入栈 3、入栈 8、弹出 8、再入栈 5。两题依据各自练习代码和时点分别得到 2 与 -4。非阻断措辞意见是末题可更明确写出先减 `count` 再通过 `*out` 写入，保留模型原文。

拒绝候选 `4900be4d173786aecbba0f1a2f2b7c2d6a8ae136b348592685848e46d7d8a20d` 和完整双场景课程通过十一项独立审核，保存 v3。实际请求绑定本批正常场景版本 `57dd6df0-5691-4071-9e46-90e369743a76`、摘要 `b1d7441b2654037d32417ecebb2cfb3563a5eeee3d6dab4b759d8ee752fff63e` 及该版正文。拒绝演示 f4 与 f8 命中守卫行 9 与 16，均返回 `false`，逻辑栈、底层槽、计数和旧输出均保持。f8 保留的 3 来自上次成功出栈。四题使用各自练习证据，结果为 3、0、1、A。非阻断意见是第 3 段可明确「第 4 次调用返回 `false`，记录为 `ok_4`」，保留原文。

### 实际私有学习验收

课程 ID `f8750937-736e-427f-8eb3-5d60288ae314`，完整版本 v3，操作 `59aac7b5-1f71-48b4-9bbb-072698fd5342` 在 STOP 后读回为 `succeeded`。新大纲摘要 `c653bd406f5f5c33c6e9c6d291a968bc157daae380d01391aa82e14fae8ad780` 绑定 T147 已审核 B 选择。运行 `sh /tmp/edumind-t151/open.sh B` 可用本批私有访客打开本机开发应用。

Chromium 读完两场景，核对 5＋9 帧的栈状态、出栈值和高亮，以及播放、暂停、前后步、重置。两组 2＋4 题均分别提交全错和全对作答，服务端匹配率为 0% 和 100%，共四次本机练习提交。答前无答案键或解析，其他访客无法读场景和作答记录。刷新保持 v3、场景、已填答案和反馈，切回正常场景仍可读取该组反馈。无重复提交或页面错误。[B 浏览器验收](t151-browser-B.json)

### 用量与原件

| 场景 | HTTP | 输入 / 输出 token | 请求 SHA-256 | 响应 SHA-256 | 审核 SHA-256 |
| --- | ---: | --- | --- | --- | --- |
| 正常 | 200 | 3470 / 660 | `d956501610a26bc62099f8036d5d3deb03acc5b73939661ca6f3275bf16e1824` | `62093cec6bdf52a13e5ddb62e588caf43366b17e915835917b8277026cb133de` | `354efe3b9f4fc680bc183be9451a8d48c2fc423956dc9e646cbb4fc48f86608c` |
| 拒绝 | 200 | 6595 / 1204 | `bd79114c48773a5947e35ab7a4d41bcf0857c352ed93097bf55f90bf4ecf486d` | `9e46c99876705b14a39beb4542d7ecf0fcecde69c92291d46c9ee93bb35c512b` | `c0b5b153935b9d64dc26a1eff8f4912e5c50a277d8e8b52f2f49e512e1ebc996` |

实际 **0 次选择、2 次正文、0 次修订**。回执合计输入 **10065**（其中缓存命中 1536）、输出 **1864**，共 **11929** token，实际账单未知。原件、预约、回执、两次审核和准入记录封存在 `~/.local/share/edumind/stack-goal-b-retest-v1/`。

使用 `sh /tmp/edumind-t151/run.sh inspect normal` 和 `inspect rejections` 重放原件，使用 `PYTHONPATH=backend:. backend/.venv/bin/python /tmp/edumind-t151/check-browser.py B` 和本机私有 API 完成验收。STOP 已封存，后续入口在读取密钥前返回 `STACK_BATCH_STOPPED`。T149 的 401、STOP 和 A v2 仍在，T147/T149/T038 历史任务状态保留。

## T152 C 私有范围提示

现有 `awaiting_clarification` 状态、私有课程和操作读取接口可承载范围提示。现有规划准入只接受当前请求的响应，T147 原规则拒绝 C 的两条引文。限定导入的最小差异是复用 T148 重放与独立审核，只接受这份 C 原件，在原访客的新私有目标记录中写入 `awaiting_clarification`，原因标记为 `STACK_SCOPE_ARCHIVED`。操作策略快照保存旧课程和操作 ID、原请求与响应摘要、证据规则、两条原文引证和独立审核。该操作仅提供范围提示，沿用限定操作的私有读取及后续生成拒绝规则。没有新增 API、表或模型执行入口。

原样保留 `request_1` 的 `normal`「理解栈操作」及 `unsupported`「动态扩容」。已重验 T147 的加密响应、请求和 STOP，并逐字段核对 T148 审核派生结果。旧 C 操作仍为 `cancelled`，原失败仍为 `STACK_SELECTION_EVIDENCE`。[T148 原件和审核绑定](t148-scope-replay.json)

新私有目标记录为 `9f428f9d-c6d6-4f69-8e43-8ff3b1785d55`，操作为 `017c9f3f-07db-477a-8072-5fbd50c2774f`。页面显示「当前支持固定容量栈的正常操作及满栈、空栈拒绝。动态扩容暂不支持。」原访客的两小时会话已过期，验收在同一专用库为该访客建立新的标准两小时本机会话，旧会话记录保留。在本机运行 `sh /tmp/edumind-t152/open.sh` 可打开提示，也可在该会话进入「学习记录」，选择最新的「理解栈操作和动态扩容」，再点击「查看生成进度与继续选项」。[本机开发应用](http://127.0.0.1:5222/)

| 定向检查 | 实际结果 |
| --- | --- |
| 原访客从学习记录进入 | 私有课程及操作均为 HTTP 200，显示完整范围提示。 |
| 刷新和调整目标 | 刷新返回同一操作和提示。返回目标页修改输入，浏览器发出 0 次 POST。提示页无继续生成入口，现有服务拒绝从该操作提交澄清（`OPERATION_KIND_INVALID`）。 |
| 其他访客访问 | 课程及操作均为 HTTP 404。 |
| 私有库和模型调用 | 重复导入返回同一操作。新记录仅有 1 个操作，规划、课程版本、场景正文版本和发送预约均为 0。Provider 0，A/B 未重跑。 |

实际验证命令为 `PYTHONPATH=backend:. backend/.venv/bin/python /tmp/edumind-t152/check.py`，使用本机 Chromium 和专用 PostgreSQL，结果保存在 `/tmp/edumind-t152/verification.json`。变更文件通过定向 Ruff、ESLint 及 `git diff --check`。

## T154 B v3 事实与答案取证

对 T151 私有 v3 的两个准确场景做只读取证。正常场景 v2 的场景版本由 v3 原样引用。封存候选、实际可见投影、两份独立审核和四份代码均有摘要绑定。实际受委托助手按块内同义合并、不同可见块及帧属性各记一项的口径，核对 18 个可见块、14 帧和六条反馈解析。事实 **348 项，正确 348、错误 0、未决 0**。该分母仅为本课可见事实，判卷边界单列。[取证明细](t154-fact-answer-evidence.md)

**六题题义、唯一答案和解析均正确，完整判卷边界 0/6。** 只读复核既有四条标准正反作答，六题原反馈正确。实际服务使用 `short_text` 的 `quiz-exact-text-v1`，逐题纯函数复现五道整数题拒绝等值表示，且 `guard_pair` 接受题面明确排除的小写 `a`。准确题键、七个输入边界和匹配率影响见明细。保留原文和 T151 的原审核，本次新增的匹配结论不回写历史。

Provider 调用、应用写入和新作答均为 **0**。本次是开发取证样例，评估身份为 `delegated_assistant`、`independent_human_truth=false`。T038 不新增正式分子或分母。

## T155 B v4 练习输入与判卷

对同一私有课程发布 v4，清单 `88b818cf-f5a9-49e7-a849-12d259cf3bda`，操作 `f748bd10-c529-4cfd-ae59-250091709db9`。从准确 v3 快照应用程序规则 `stack-b-program-exercise-format-v1`。原子写入两个场景、两组练习和一个课程清单，沿用原大纲。新拒绝场景的应用依赖指向新版正常场景。原模型候选、审核及模型请求的历史依赖继续指向原版。维护操作保存父版本摘要与派生字段，模型用量为零。[版本化维护命令](../../../scripts/revise_stack_b_exercise_format.py)

| 场景 | 新场景版本 | 新练习版本 |
| --- | --- | --- |
| 正常 | `2a8c592d-0366-497d-bb48-e053599d3380` | `95b2dc24-7f41-5b60-aed2-1f869d720699` |
| 拒绝 | `0283a5a1-5df3-44b3-9f19-233bb426c2ac` | `254f8295-e506-5f69-8aac-a86eafac0dad` |

五道整数题采用现有 `integer` 和 `free-course-typed-json-v1`。题面保留原条件和范围，示例提示使用 JSON 整数（如 `12`、`-7`）。`guard_pair` 仍按文本比较，题面提示输入 A 或 B，大小写均可。比较反馈沿用原比例和参考解析。带「请输入一个 JSON 整数，不附加文字」的反馈表示格式未通过、未比较数值。合格式但值不同时显示不匹配和原解析。正号、前导零或数学减号 `−` 的写法可能表达等值数学答案，在这里属于格式不合要求。

| 定向检查 | 实际结果 |
| --- | --- |
| 六题标准与 T154 边界 | 六题标准全匹配。`-0` 按 0 匹配，`a` 按 A 匹配。 `+2`、`-04`、`−4`、`+3`、`+1` 返回格式提示。 |
| JSON 类型及数值反例 | 小数、指数表示、字符串、数组、布尔值和 null 返回格式提示。合格式错误值及 B/b 返回不匹配。共 22 个比较用例。 |
| 实际 Chromium 页面 | 两场景均显示题组格式示例，新版五题有 JSON 整数提示，守卫题有大小写说明。两组标准作答均为 100%。补充作答显示格式提示与数值不匹配的差异，以及 `-0` 和 `a` 的匹配。答前未返回参考键或解析。 |
| 版本隔离 | 两组刷新恢复原输入、反馈及 v4 绑定，未重复提交。切换 v3 显示旧题面并只读，新版草稿不串入。四条原 v3 作答的内容、反馈、版本标识和摘要全部一致。重跑发布命令返回同一 v4。 |
| 内容与范围 | 精确快照核对确认两个场景的模型文字、解析和来源、程序代码、十四帧状态与动作、参考键均未改。沿用 T151 的十四帧和播放器实测。只有练习输入说明及类型发生变化。本次 Provider 和发送预约均为 0。 |

[本机开发应用](http://127.0.0.1:5222/) 使用 T151 B 原访客身份，从「学习记录」打开「先学压入弹出，再看塞满时压不进、一个也没有时弹不出的原因。」，选择 v4 的场景。浏览器验收使用原访客的新标准两小时本机会话，私有访问规则不变。

实际检查运行 `PYTHONPATH=backend:. EDUMIND_CATALOG_TEST_PG_CONTAINER=edumind-phase1-t037-pg backend/.venv/bin/python /tmp/edumind-t155/env.py -m scripts.revise_stack_b_exercise_format` 与同一环境下的 `/tmp/edumind-t155/verify.py`，以及 `backend/.venv/bin/python /tmp/edumind-t155/browser.py`。命令的场景与练习标识、比较矩阵、出入参分类和四次浏览器作答均已归档。[定向检查证据](t155-exercise-format-verification.json)

T154 缺陷和旧成绩仍属于 v3。此次是程序练习格式版本更新，T038 未新增正式质量结果。
