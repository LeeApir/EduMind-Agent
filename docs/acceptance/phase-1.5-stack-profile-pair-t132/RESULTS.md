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
