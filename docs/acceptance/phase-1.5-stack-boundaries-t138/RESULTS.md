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
