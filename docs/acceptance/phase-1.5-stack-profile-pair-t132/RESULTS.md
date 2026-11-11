# T132 同材料栈课程的最小画像对照

## 准备结果

两份准确输入与请求已冻结，Provider 调用 **0 次**。两份请求使用同一栈学习目标、固定提纲、系统提示、模型参数、输出 Schema 和程序材料。唯一变化是用户载荷中的 `learner_evidence`。

共同目标为理解栈顶、入栈、出栈和后进先出，追踪从空栈开始执行 `push(3) → push(8) → pop() → push(5)` 的每步栈内容、栈顶与出栈结果。程序继续持有 C 代码、五帧状态与高亮位置、事实、练习场景及参考答案。共享材料摘要为 `05381e097f08e1c39d9747859d49c8cdb3a5df0dbb1c88f0e4a9f819077a2660`，固定提纲摘要为 `b5a04d884e6b987dbbf017141074ab2e50dbaa37c47a40112688efd1bf8e0124`。

| 测试画像 | 准确输入及请求 | 输入 SHA-256 | 请求 SHA-256 |
| --- | --- | --- | --- |
| A · 我只掌握数组基础，这是第一次学习栈。 | [输入](array-first/input.json) · [请求](array-first/request.json) · [清单](array-first/manifest.json) | `94c3bd2261fc16b35a3526da0f76d5c498e7c6367eaae45feb98b88945c97389` | `0b2079e5cc7ce5808cbab867d4b14580ec3731d66fabbee471a83653e36d1895` |
| B · 我已理解栈操作，需要解释边界与实现。 | [输入](operations-known/input.json) · [请求](operations-known/request.json) · [清单](operations-known/manifest.json) | `a1ca71ac5fdbfd39705babf4a4c4b7c5ea9013c204c0342d3ad224989fbbe267` | `6559b08ca8cfb2b009ac826a32b00f846c1d74bd557c266907ac30e642ec6dc2` |

两份画像是独立测试访客的合成自述。B 的“边界与实现”只指定讲解重点，共同目标原样保存。未提供的背景、能力和偏好字段均为未知。证据时间与置信字段来自冻结测试夹具，无测验成绩或真实学生个人资料。发给模型的画像载荷不含访客 UUID、数据库画像 UUID 或真实用户数据。

## 接线及复用

| 现有能力 | 本次用法 |
| --- | --- |
| `profile_schema` 与 `profile_updates` | 校验显式自述、证据版本和空值，在隔离库中持久化两份不可变测试画像。未使用模型推断画像。 |
| `SnapshotRepository.create_course(profile_id=...)`、`free_course_planning.load_inputs`、`free_scene_generation.load_inputs` | 固定课程创建时保存所属访客的版本化画像快照，再走原规划和场景输入加载。提纲仍由程序固定，规划输入加载不产生规划请求。 |
| `stack_course_materials` 与 `course_trial_generation` | 在固定栈请求中增加有来源的画像证据。共用传输以实际请求字节封存并回放。候选摘要绑定画像版本及证据快照、请求响应、材料和提纲。 |
| `course_trial_publication.assembly` | 保留栈完整教学审核条件，另需确认遵守画像证据及讲解深度适合本画像。审核必须绑定本候选并确认已做全文审核。 |

画像对照适配只在专用隔离库和 MockTransport 验证，真实发送及应用准入保持关闭。后续真实批次需另行确定额度和批准记录，并接通这两份候选的私有准入。旧栈请求原字节和历史批次保持。

## 事前教学对照

两份完整课程都先接受相同的事实、代码、帧、练习题义、答案及解析审核，再按下表逐项比较。审核记录须引用两课对应段落或帧及其事实 ID。仅调整称呼、标题或同义措辞视为未满足对照。

| 检查项 | A 的可观察要求 | B 的可观察要求 |
| --- | --- | --- |
| 术语铺垫 | 正文先解释栈顶、入栈、出栈、后进先出，再用数组中 `count` 表示的有效前缀连接已有知识。 | 简短回顾同组术语，把主要解释用于 `count` 与栈顶下标的不变量，以及为何只有非空时能读取栈顶。 |
| 过程详略 | 按顺序解释四次操作的状态变化，明确为何第一次出栈得到 8、随后栈顶为 3。 | 五帧仍完整且正确，概念性复述简洁。结合入栈写入后加一、出栈先减一再读取原顶槽，解释为何这些顺序正确。 |
| 边界与实现 | 用直接语言说明满栈及空栈拒绝、`bool` 与 `*out` 的区别，并说明主例只演示成功分支。 | 明确 guard 先于写入或减一，失败时状态不变、失败的 `pop` 不改 `*out`；解释固定容量不扩容和旧槽仍有值却不属于有效栈。 |

任一课程出现不支持的画像推断、材料漂移、事实错误或全文审核阻断，记录准确位置。最终两课都要分别通过全文审核和实际页面学习验收，然后比较上述三项差异。固定单场景的一对合成画像只验证 M06 的画像接线和教学对照，尚未覆盖 T038 的六对画像、可变场景及跨场景依赖。

## 离线验证记录

在专用 PostgreSQL `edumind_catalog_p15_t132_stack_profiles_test` 执行 `alembic upgrade head`。使用 `scripts.run_catalog_db_tests.test_environment` 构建专用连接，并在 pytest 进程安装 `scripts.head_course_goal.raw_io_audit` 禁止外网。

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -c '
import sys, pytest
from scripts.head_course_goal import raw_io_audit
sys.addaudithook(raw_io_audit)
sys.exit(pytest.main(sys.argv[1:]))
' -q backend/tests/test_stack_course_profile_pair.py --tb=short
```

实际 **2 项通过，0 跳过**。共用发送路径捕获两个 MockTransport 请求，逐字节匹配冻结原文；从加密封存严格回放。错画像、错请求摘要、交叉审核、不完整审核、真实发送及应用准入均被拒。两份模拟候选使用相同夹具正文，结果只证明绑定及审核门禁。Ruff、账本工作流和 Git 差异检查通过。真实课程、教学对照结论及页面验收待另行授权后写入本记录。

## T133 真实批次准备与待授权范围

接线及离线验证完成，真实 Provider **0 次**，尚未建立真实窗口。拟批准 **0 次规划、2 次正文、0 次修订**，每槽一条正文，无重试、回退或探测。

| 执行项 | 冻结值 |
| --- | --- |
| [共同清单](live/manifest.json) SHA-256 | `e6265ed240d70f9e9eb58b3bce5b66d6c00a9660693a1b2b64944d7677174f94` |
| 槽 A | `--topic stack-profile-array-first` · [原请求](array-first/request.json) · [批准模板](live/array-first.approval.template.json) |
| 槽 B | `--topic stack-profile-operations-known` · [原请求](operations-known/request.json) · [批准模板](live/operations-known.approval.template.json) |
| 模型和参数 | 两槽使用 T132 原始字节及 DeepSeek 官方 `POST /responses`，`deepseek-flash`，`temperature=0.2`，`reasoning.effort=none`，`stream=false`，`store=false`，`max_output_tokens=4000` |
| 时间 | 建议先 A 后 B。每槽创建操作时起算 1,800 秒，发送前预留 90 秒 I/O 限制，准入在各槽有效窗口内完成。两槽窗口合计最多 60 分钟，间隔按实际登记。浏览器验收可随后完成 |
| 费用和原件 | 最多 2 次 HTTP，参数合计最多 8,000 输出 token；严格校验每槽输入回报 ≤139,264、输出回报 ≤4,000。回报校验不能约束服务端收费。实际金额未知，无可验证费用硬上限；尽力停止后仍可能迟发或计费，本机原件无独立抗回滚保障，服务端留存未独立确认 |

[ADR0065](../../ADR/0065-stack-profile-pair-live.md) 集中记录本批范围与 C2 边界。两份模板的真实授权及 C2 确认为 `false`，只能在获准后登记为真实批准。冻结文件继续使用 T132 的准确输入、请求和上文三项教学标准。

### 实际入口与记录

使用专用回环开发库 `edumind_catalog_p15_t127_reuse` 及现有开发应用。获准后先重载开发 API。各槽建立独立合成访客，用现有 `persist_profile_version` 持久化 `stack_course_profile_pair.profile_snapshot(case)`，取得 `OWNER` 和 `PROFILE_ID`；读取实际画像快照时核对所属者、版本及证据。两槽的私有课程用各自访客会话验收。无需模型生成画像。

```sh
export PYTHONPATH=backend:.
# SLOT 为 stack-profile-array-first 或 stack-profile-operations-known
backend/.venv/bin/python -m scripts.course_trial inspect --topic "$SLOT"
# 仅在批准后运行，prepare 回执登记本槽 starts_at / expires_at
backend/.venv/bin/python -m scripts.course_trial prepare --topic "$SLOT" --owner "$OWNER" --profile-id "$PROFILE_ID" --approval "$APPROVAL"
backend/.venv/bin/python -m scripts.course_trial send --topic "$SLOT"
backend/.venv/bin/python -m scripts.course_trial replay --topic "$SLOT"
# 准确的本次独立全文审核落盘后，在窗口内准入
backend/.venv/bin/python -m scripts.course_trial publish --topic "$SLOT"
# 遇到结构失败、教学阻断、准入失败或未知结果，停止该槽
backend/.venv/bin/python -m scripts.course_trial stop --topic "$SLOT"
```

发送凭据仅在本机终端隐藏提示输入。两个固定原件目录分别为 `~/.local/share/edumind/stack-profile-pair-live-array-first-r01/` 和 `~/.local/share/edumind/stack-profile-pair-live-operations-known-r01/`。各保留请求、尝试、加密响应、收据、候选、审核和准入或失败记录。每槽一次性 STOP 禁止再次发送；显式停止产生 HALT 并阻止准入。另槽依照各自批准执行。

每课 `review.json` 要求准确候选摘要、`parent_digest=null`、`full_lesson_reviewed=true`、独立评估人、阻断项、既有栈审核项及 `evidence_kind=actual_provider_response`。分别记录 `learner_evidence_respected` 和 `teaching_depth_matches_profile`。前者须通过；后者须如实填写，允许正确且可学的课程在深度不足时仍交付。页面显示 A/B 来源，私有快照与版本绑定请求、响应、画像证据和审核摘要。

每课完成实际阅读、五帧高亮、播放控制、四题反馈及刷新恢复，核对答案隔离。两课验收后，按原表的术语铺垫、过程详略、边界与实现逐项引用 A/B 的段落或帧及事实 ID。三项均有充分且符合画像的差异才记对照通过。两课正确而差异不足时，保留两课，记录对照未通过。将实际窗口、用量、独立审核、学习入口、浏览器证据及对照判定追加到本记录。

### T133 定向验证

专用回环 PostgreSQL `edumind_catalog_p15_t127_reuse_test` 执行 `alembic upgrade head`。使用上文相同的禁外网 pytest 入口运行 `backend/tests/test_stack_course_profile_live.py`，**1 项通过，0 跳过**。测试通过共用发送和封存回放逐字节核对两个请求，拒绝交叉授权、错总额度、真实路径读取夹具原件、重复发送、修订、错响应来源、交叉审核及缺少全文审核。两槽均验证深度不足仍可私有准入，跨访客读取返回 404，作答前响应不含答案。两份离线夹具及模拟审核只用于验证门禁。CLI 摘要、Ruff、Vue 类型、账本与 Git 差异检查通过。

## T134 真实批次登记

用户已批准提交 `a98e3e2` 对应共同清单、两份准确请求及 ADR0065 C2。登记 [A 槽授权](live/array-first.execution-approval.json) 与 [B 槽授权](live/operations-known.execution-approval.json)。授权各 1 次正文，规划及修订 0 次。登记时尚未创建操作窗口，Provider 0 次。

## T134 真实结果

两槽额度均已使用。**A 首稿结构和独立全文审核通过，私有 v2 已交付。B 首稿结构失败，保留原件并取消操作。画像对照未完成。**

| 槽 | 北京时间窗口 | HTTP 和 Provider 回报 | 候选、审核与课程 |
| --- | --- | --- | --- |
| A · 数组基础、首次学习栈 | 2026-11-11 15:23:31–15:53:31 | HTTP 200；3,003 输入、1,391 输出，缓存和推理均 0 | 候选 `783f8563040e9abb02ead329660f8aab8a26def2987b656078a9f8f526bbb111`；独立全文 9 项通过，15:27:52 窗口内准入回执。私有 v2 课程 `4ec7a96d-4809-466b-9eb7-4d8409dc7351`，场景版本 `c9de4591-3f5e-46e0-ad50-8165eca45e3a`。[审核](live/array-first.review.json) · [浏览器](live/array-first.browser.json) |
| B · 已懂栈操作、关注边界和实现 | 2026-11-11 15:28:52–15:58:52 | HTTP 200；3,053 输入、1,215 输出，输入缓存命中 1,152、推理 0 | `ROLE_SCHEMA`。原正文 `paragraphs` 仅 3 段，低于冻结 Schema 的最少 4 段。无合格候选、全文审核或可学场景。操作 `0a660ed7-28c1-47aa-ac70-c14affae5ffc` 已取消，课程仅 v1 提纲。[失败证据](live/operations-known.failure.json) |

原件按两个固定目录保留。A 原响应 SHA-256 `0ed21532be3257ce44be99482216ebc8ea7c0055980a571ec504b220c4e30512`，严格回放与冻结请求一致；本次独立审核规范 JSON SHA-256 `9e3455d7989f8bd6d84fa176bdaa1b459135438c0c280a6c18c9fa04c341c2de`。B 原响应 SHA-256 `9b72b77a3a5059ab7f9a734f41029db0adfbfc6a05b19f9126d561e28993c95a`，原件复核为唯一一处段落数量错误，STOP、HALT 和失败收据保留。总计 0 规划、2 正文、0 修订，6,056 输入、2,606 输出 token。无重试、回退或探测，实际账单金额未知。

**学习入口。** 在本机终端运行 `sh /tmp/edumind-t134/open.sh A`，使用 A 槽原访客打开 [EduMind 开发应用](http://127.0.0.1:5217/) 的私有栈课。实际 Chromium 已核对正文四段与总结、五帧和高亮、播放与暂停续播、步进及重置。四题全错和全对分别得到 0% 与 100% 反馈，作答前未下发答案及解析，跨访客场景和作答均 404，刷新恢复同版且新增提交 0。独立审核记录两项非阻断意见：正文“字节”可更精确为“数组槽位”，部分题干的“程序随后追加”略显冗余。

**对照判定。** 按事前标准，术语铺垫、过程详略和边界与实现均记为未评，原因是 B 未形成通过审核的完整课程。A 的术语、过程与实现证据见其审核，封存的 B 失败正文留作诊断。没有改原标准或追加调用，保留 A 已通过的私有课程。

## T134 补充：B 封存正文只读复核

**结论。** B 的结构拒绝只由段数触发，`paragraphs` 有 3 段，冻结 Schema 要求至少 4 段。共同学习目标的基本内容齐全，五帧、四题及解析完整，未发现栈状态、代码动作或参考答案的错误。但按 B 画像的原教学标准，**确实缺少实现原因的讲解**。它说清了有效范围、栈顶下标以及入栈和出栈的代码顺序，对「为何这个下标成立、为何必须按该顺序访问槽位」的说明不足。单独拆成四段不会补上这部分。B 对边界已有实质讲解，尤其是成功取出 0 与失败的区别；这个增量不足以让三项画像对照都达到原标准。

以 A 通过审核的候选和 B 原响应为依据。只读解封后复核两份请求均与冻结字节一致，响应明文摘要与封存回执一致。按原 Schema 重新枚举错误，B 仅有 `paragraphs/minItems`。另核对引用 ID、帧顺序、题干规则、私有参考答案和原独立预期。以下段落编号从 1 开始。

### 逐段与总结

| B 原文依据 | 事实与教学判断 | A 对应证据 |
| --- | --- | --- |
| 第 1 段，`order`、`push`、`pop`、`lifo`。「count 记录有效元素个数」「非空时栈顶就是 data[count-1]」；「先把新值写到 data[count] 并增加 count」「先检查空栈，再减小 count」。 | LIFO、有效元素、栈顶和 push/pop 顺序正确。给出了非空条件和正确下标，但没有说明空栈时没有有效末槽，也没有在这里把写前的 `data[count]` 是首个空槽、减一后的 `data[count]` 是原栈顶这两个关系说清。容量 3 与程序一致，段内可直接支持该声明的 `boundary` 引用在第 2 段。 | A 第 1 段用「有效元素只占 data[0..count) 这一段」引出末槽，定义范围与操作同样集中，引用 ID 相同。 |
| 第 2 段，`boundary`。「失败时状态不变，且失败的 pop 不写 *out」「count 之外的旧值不是逻辑元素」「调用者能区分‘失败’和‘成功但值为 0’」。 | 满栈、空栈、容量不扩容、有效指针、旧槽和输出参数均有覆盖。零值区分是可由代码推出的有效说明，主例没有实际执行该分支。旧槽为什么失效须结合第 1 段的有效范围阅读。 | A 第 2 段也给出两个 guard 和 `bool`／`*out`；第 3 段另有「那个位置已经落在有效区间之外」的直接因果说明（`order`、`pop`、`boundary`）。 |
| 第 3 段，`f0`–`f4`。「五帧都是已完成的调用者语句，全部成功」「pop 帧移除 8，而当前栈顶变为 3」。 | 主例序列、帧的展示边界和移除值与新栈顶的区别准确。没有把满栈或空栈拒绝说成已演示，逐步状态由五条帧说明承接。 | A 第 4 段也用「移除的是 8，而移除后栈顶变成 3」说明该区别，并另引 `lifo`。 |
| 总结。「主例中 8 先被移除，3 成为新栈顶，最后 5 入栈成为栈顶」「失败的 pop 不写 *out」。 | 复述了主要结果、边界和旧槽含义，无新事实错误。 | A 总结另外列出四次操作后的栈内容 `[3] → [3,8] → [3] → [3,5]`。 |

未见额外推断学习者的 C 熟练度、背景或偏好。B 的「有效元素是 data[0] 到 data[count-1]」结合非空条件和 f0 阅读，含义与程序一致，解释深度仍见上表。

### 逐帧

| 帧／程序高亮 | B 原文依据与核对 | A 对应差别 |
| --- | --- | --- |
| f0／22 | 「count 为 0，没有有效元素，栈顶为空。」空栈、无栈顶准确。 | A 明写 `data[0..0)` 为空区间。 |
| f1／24 | 「3 写入 data[0]，有效元素为 [3]……栈顶是 3。」写入位置、结果和栈顶准确。帧内并列说明计数与写入，代码顺序以第 1 段为准。 | A 还说明先确认未满、再写入、再增加 `count`，并把栈顶对应到公式。 |
| f2／25 | 「8 写入 data[1]，有效元素为 [3,8]，栈顶是 8。」与程序一致。 | A 说明原 `count=1` 小于容量 3，并按写入、更新计数、返回成功展开。 |
| f3／26 | 「count 从 2 减为 1，原栈顶 8 通过 *out 写入调用者变量」「当前栈顶是 3」。出栈值与新栈顶均准确。 | A 明确读取原槽 `data[1]`，并解释该槽未清零却已在有效区间外。 |
| f4／27 | 「5 写入 data[1]，有效元素为 [3,5]，栈顶是 5。」与程序一致。 | A 指出写入覆盖旧值，并给出先写后增的动作顺序。 |

### 逐题

| 题键 | B 原文依据与核对 | A 对应差别 |
| --- | --- | --- |
| `first_pop` | 题干指定「第一次 pop 成功时写入 value」并要求整数。解析「移除当前栈顶 2」，唯一答案 `2`。 | A 还列出出栈前的 `[-4,6,2]`，并解释先减计数再读原栈顶。 |
| `after_push` | 题干指定第一次出栈后再入栈 9，按栈底到栈顶答 JSON 整数数组。解析从 `[-4,6]` 推到唯一答案 `[-4,6,9]`。 | A 还交代原 `count=2`、写入 `data[2]`、新 `count=3`。 |
| `pop_order` | 题干指定三次 pop 写入值并要求按发生顺序答数组。解析依次说明取 2、9、6，唯一答案 `[2,9,6]`。 | A 同样给出这一推演，解释深度接近。 |
| `final_top` | 题干指定最后一次 pop 之后的当前栈顶并要求整数。解析「只剩 -4」，唯一答案 `-4`。 | A 额外说明 `count=1` 和 `data[count-1]`。 |

B 四题均与附加代码的操作顺序一致。题干重述了输入序列和作答时点，未回抄 C 语句或直接给出答案。四条解析齐全，参考答案仍由程序持有。

### 按原三项标准的只读对照

| 原标准 | 只读判定 |
| --- | --- |
| 术语铺垫 | **差异不足。** A 第 1 段与 B 第 1 段均用 LIFO 开场，紧接有效前缀、栈顶公式与 push/pop。B 有简要回顾，和 A 的铺垫结构接近，未进一步解释为何非空条件使栈顶访问成立。 |
| 过程详略 | **可见差异，未充分。** B 的 f1、f2、f4 和逐题解析确实比 A 精简，五帧仍正确；B 第 1 段说明顺序、f3 说明结果，对「为什么先写后增、先减后读能保持有效范围并定位原顶」仍缺一层因果讲解。 |
| 边界与实现 | **有实质增量，整体区分有限。** B 第 2 段的成功取出 0 与失败之分是独有增量。两个 guard、失败不改状态和旧槽无效在两课都已覆盖；旧槽失效原因在 A 第 3 段和 f3 反而更直接。 |

以上是失败原稿的教学诊断。正式画像对照仍未完成，B 的结构拒绝和停止状态保持。新增 Provider 调用 0，封存原件、正文和应用数据均未写入。

## T135 画像提示词 v2 准备

A、B 共用 `stack-learner-evidence-v2`，使用 T132 原画像证据。v2 的变化集中在系统提示。模型自行组织 4–7 个有实质内容的 `paragraphs` 项，帧说明、总结和题解不计入段数。提示只给教学职责和证据指路，保留模型组织段落、论述和措辞的空间。代码、五帧、练习场景、参考答案、输出 Schema 和原三项对照标准均沿用 T132。

| 共用教学职责 | 对应程序依据 | 审核时核对的因果说明 |
| --- | --- | --- |
| 有效前缀与栈顶 | `Stack.count`、初始化第 22 行，`order`、`f0` | 计数如何界定有效下标，末槽为什么只有非空时存在。 |
| 入栈的写入和计数顺序 | C 第 9–10 行，`order`、`push`、`f1`／`f2`／`f4` | 写入前的 `count` 为什么指向第一个可用槽，以及增加计数后新值为何属于有效前缀。 |
| 出栈的计数和读取顺序 | C 第 16–17 行，`order`、`pop`、`f3`、`boundary` | 减一后的下标为什么指向原顶，移除值和新栈顶如何区分，旧槽为何无需清零也会失效。 |
| 失败边界和输出 | C 第 8、15 行的 guard 及第 17 行写出，`push`、`pop`、`boundary` | 守卫在任何修改前返回，因此失败不改栈，空栈 pop 也不写 `*out`。区分成功标志、数据值、固定容量和主例只演示成功操作。 |

A 用数组槽位和逐步状态解释这些关系，保留有帮助的实现说明。B 简要回顾术语，在相同正确性要求下把篇幅集中给不变量、更新顺序的原因及边界。两课可以共享必要知识。审核应逐段、逐帧和逐题核对正确性，再用原三项标准引用两课证据比较教学重心；仅列公式或复述代码顺序不能视为解释了原因。两课各自通过与画像差异是否充分仍分别记录。

| 槽 | 准确请求 | 字节 | SHA-256 |
| --- | --- | ---: | --- |
| A · 首次学习栈 | [v2 A](prompt-v2/array-first.request.json) | 12,371 | `cb5b0e4863f7fa973beef1922451fe7ec04fcbabc1b49e696e0f4bcb335c11df` |
| B · 关注边界和实现 | [v2 B](prompt-v2/operations-known.request.json) | 12,536 | `278a86dd2e546b4f0b072409c2ba46939da1b4f1a1f7ec1a9c1e139e84352abd` |

`PYTHONPATH=backend:. backend/.venv/bin/pytest -q backend/tests/test_stack_course_profile_prompt_v2.py` 定向 **3 项通过**。逐字节核对 v1 与 v2，确认各槽只变更系统提示；移除 `learner_evidence` 后，两份 v2 请求完全一致。用共用请求构造、响应校验和候选绑定的离线夹具验证 v2 正常绑定，以及拒绝 v1 请求、对方槽请求和互换的画像证据。夹具只用于检查接线，Provider 调用 0。Ruff、工作流和 Git 差异检查通过。

拟下一批同版 A/B 各生成一次正文，合计 **2 次正文、0 次规划、0 次修订**。此处仅冻结请求和检查，尚未登记 v2 真实发送入口、窗口或授权。后续另行确定准确执行包，A 与 B 一并使用 v2；T134 的 A 保留为已交付课程，B 保留为失败诊断。旧批复现沿用其冻结运行提交 `a98e3e2`。

## T136 v2 准确执行包待批准

A/B 使用 T135 两份冻结请求，进入独立 r02 槽。离线接线已验证，Provider **0 次**，未登记真实窗口。拟议范围及费用例外见 [ADR0065 v2 补充](../../ADR/0065-stack-profile-pair-prompt-v2.md)。

| 项目 | 冻结值 |
| --- | --- |
| [共同清单](prompt-v2/manifest.json) SHA-256 | `de148d78ffa49917294a21c65d32dfa91007a7432f8f4680c5d516be92abdd14` |
| A · `stack-profile-array-first-v2` | [原请求](prompt-v2/array-first.request.json) `cb5b0e4863f7fa973beef1922451fe7ec04fcbabc1b49e696e0f4bcb335c11df` · [批准模板](prompt-v2/array-first.approval.template.json) |
| B · `stack-profile-operations-known-v2` | [原请求](prompt-v2/operations-known.request.json) `278a86dd2e546b4f0b072409c2ba46939da1b4f1a1f7ec1a9c1e139e84352abd` · [批准模板](prompt-v2/operations-known.approval.template.json) |
| 调用 | 0 规划、2 正文、0 修订，各槽各一次。DeepSeek 官方 Responses `deepseek-flash`，`temperature=0.2`，`reasoning.effort=none`，`stream=false`，`store=false`，`max_output_tokens=4000` |
| 窗口 | 建议 A 后 B，各槽 `prepare` 创建操作起 30 分钟。发送前预留 90 秒 I/O 限制，审核及准入在各槽窗口内。两窗口满额合计 60 分钟，间隔按实际登记 |
| C2 | 最多两次 HTTP；实际费用未知，无可验证硬上限，停止后仍可能迟发或计费，本机原件无独立抗回滚保护，服务端留存未独立验证 |

两份批准模板保留 `explicit_user_authorization=false` 和 `accept_T136_scope_and_batch_C2=false`。待准确授权后按 T133 相同流程在专用本机开发库为两槽建立新合成访客和画像，重载本提交的 API。共用命令参数仅替换为表中的 v2 topic，继续使用 `inspect → prepare --owner ... --profile-id ... --approval ... → send → replay → publish`，失败用 `stop`。发送密钥只在本机终端隐藏提示输入。各槽使用 `~/.local/share/edumind/stack-profile-pair-live-array-first-r02/` 或 `~/.local/share/edumind/stack-profile-pair-live-operations-known-r02/` 保存原件。一槽失败即封存并停止该槽，无重试或回退，另一槽独立执行。

两槽独立审核核对事实和「为什么」，通过后分别验收实际阅读、五帧及高亮、四题反馈、答案隔离和刷新。最后只用两份 v2 课按 T132 原三项比较，保留正确课程，单独记录画像对照结论。T134 的 A 和 B 保留原判定和原件。

使用既有专用回环 PostgreSQL 和禁外网入口运行 `pytest -q backend/tests/test_stack_course_profile_v2_live.py`，**2 项通过，0 跳过**。实测两个槽都发送冻结字节、拒绝旧版授权及同槽重复发送，严格回放后将对应 v2 来源准入测试库；作答前无答案泄露。T135 的请求差异及绑定检查 **3 项通过**。CLI 摘要、Ruff、Vue 类型、工作流和 Git 差异检查通过。

## T137 v2 真实批次登记

用户已批准 `6b6be6f` 对应共同清单、两份 v2 准确请求及本批 C2。登记 [A 授权](prompt-v2/array-first.execution-approval.json) 与 [B 授权](prompt-v2/operations-known.execution-approval.json)。每槽仅一条正文，登记时窗口未启动，Provider 0。

### T137 A 槽真实结果

北京时间 2026-11-11 20:28:54–20:58:54。一次正文 HTTP 200，Provider 回报 3,302 输入、1,762 输出 token。原响应 SHA-256 `81a552c81a83bd3f3db13a449f04d985b7d2774d75a4b76cab10671c58271f8b`，严格回放候选 `a7d66cb8b515d12a98b6106a45236ac61efd23b6c75eb255b0d21f8248d11f49`。独立全文审核九项通过，确认正文说明了非空栈顶、先写后增、先减后读及守卫在修改之前返回的原因。审核 SHA-256 `dc0b97b5a12b2e397f446287b8bd77cda42402c0e69a4e299eac0f56772ec424`。[A 独立审核](prompt-v2/array-first.review.json)

北京时间 20:32:28 准入回执，私有 v2 课程 `0bdfa2f6-e93e-45f7-8c5b-0ee7f1cf43a6`，场景版本 `eb3c6c15-c5c2-4e5c-a1f3-0392f7c21430`。Chromium 验证五段正文和总结、五帧高亮和播放控制、四题 0%／100% 反馈、答案隔离和跨访客 404。刷新恢复同版与作答，新增提交 0。终端入口 `sh /tmp/edumind-t137/open.sh A`。[A 浏览器记录](prompt-v2/array-first.browser.json)

### T137 B 槽真实结果

北京时间 2026-11-11 20:39:19–21:09:19。一次正文 HTTP 200，Provider 回报 3,352 输入、1,508 输出 token，其中缓存输入 1,536、推理 0。原响应 SHA-256 `594eb5995c6e49f90413c40ea4b4d2ee2671ae12437852e43b9a9d046a5d006c`，严格回放候选 `2c5e487adccd66c4fc55d9dca1139bd145a51f1b5d83af92f5aea5c812a274d5`。B 首稿有 4 段，通过结构和独立全文九项检查。B 对非空栈顶的访问条件、先写后增和先减后读的因果、两个守卫先于修改的说明均准确。第 1 段的 LIFO 可补直接 `lifo` 引用，属非阻断审核意见，原文保留。审核 SHA-256 `ff978169ec66a12bf48ed57533be543850e03764af81a6a29b5030ad35676bbb`。[B 独立审核](prompt-v2/operations-known.review.json)

北京时间 20:41:22 准入回执，私有 v2 课程 `373fe95a-276f-4d1d-8a81-a0af22421b1e`，场景版本 `52d8bbd0-4d37-44de-a3cb-8bef63986f21`。Chromium 验证四段正文和总结、五帧高亮和播放控制、四题 0%／100% 反馈、答案隔离和跨访客 404。刷新恢复同版与作答，新增提交 0。终端入口 `sh /tmp/edumind-t137/open.sh B`。[B 浏览器记录](prompt-v2/operations-known.browser.json)

### T137 同版 v2 画像对照

两课均完成独立审核及页面验收。以下引用只来自 T137 的新正文与帧说明，段落按 1 开始编号。按 T132 既定标准和独立比较意见，术语铺垫与过程详略通过，边界与实现的侧重点差异不足，**画像对照未通过，两份可学课程均保留**。

| 原标准 | A 证据 | B 证据 | 判定 |
| --- | --- | --- | --- |
| 术语铺垫 | 第 1 段「data[0..0) 为空，因此没有栈顶」，f0 从初始化的数组槽位切入（`f0/order/lifo`）。 | 第 1 段简要回顾术语后解释「最后一个有效元素位于下标 count-1」，并指出空栈访问「会越界」（`order/f0/boundary`）。 | **通过。** 两课共享术语，A 从具体数组状态引入，B 直接说明访问条件。 |
| 过程详略 | 第 2–4 段逐操作带数值，第 3 段解释 f3 时写道「写入 value 的是 8」「新栈顶为 data[0]=3」（`f1/f2/f3/f4/order/push/pop/boundary`）。 | 第 2–3 段概括有效前缀「扩展为 data[0..新count)」及减一后的「剩余栈是 data[0..新count)」，具体值放在五帧（`order/push/pop/f1/f2/f3/f4/boundary`）。 | **通过。** A 用数值走完主例，B 用计数不变量概括同一过程。 |
| 边界与实现 | 第 5 段解释守卫直接返回，「不写 data[count]，也不增加 count」「不减少 count，也不写 *out」；第 3–4 段解释旧槽为何无效（`boundary/push/pop/order/f3/f4`）。 | 第 4 段说明守卫在函数开头，失败时「不写 data、不改 count、也不写 *out」；第 3 段说明 `count` 之外的旧值不属于逻辑栈（`boundary/push/pop/order/f3`）。 | **差异不足。** 两课都完整覆盖失败边界、输出参数、容量和旧槽，解释的侧重点与深度相近。B 的前缀推导已经计入过程详略。 |

本批仅 2 次正文，合计 6,654 输入、3,270 输出 token，无规划、修订、重试或回退，实际金额未知。两槽分别保留原始请求、加密响应、候选、审核、准入回执和 STOP。T134 原课及失败记录保持。T137 完成执行与对照记录，按批准范围停止。
