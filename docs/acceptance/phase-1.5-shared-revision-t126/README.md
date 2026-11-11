# T126 记录驱动的有限修订

四主题共用 `scripts.course_trial` 的离线流程。先重放通过原 Schema 和本地校验的首稿，再核对首次全文审核、允许路径和一次修订预算。准备时保存准确审核和批准记录，发送时重新核对。首稿候选、原始响应和首次拒绝准入的审核保留在原文件中，子稿和重评另行封存。

| 主题 | 可选段落字段 | 可选其他字段 |
| --- | --- | --- |
| 空链表头插 | `paragraphs[i].text`、`paragraphs[i].fact_ids` | `learning_summary`、`failure_scope` |
| 栈、队列、二分查找 | `paragraphs[i].text`、`paragraphs[i].fact_ids` | `summary` |

审核只能选择已存在的字段。程序要求定位原文或原引用 ID、说明段落职责，并将审核标为 `needs_revision`。只接受次要措辞或引用问题。返回的闭合 Schema 逐字段复用主题首稿定义。题干、解析、帧说明、程序代码、状态及答案在合并中原样保留。首稿缺必填字段或校验失败时无可修订候选。

## 命令

从仓库根运行，`EDUMIND_DATABASE_URL` 指向专用库 `edumind_catalog_p15_t126_trials_test`。以下命令使用本机测试身份和测试材料。离线发送要求完整的 Mock Responses 回执文件。首稿阶段沿用 T125 的主题流程，头插先发送 `--stage plan` 并提交对应的 `plan-review.json`。

```sh
export PYTHONPATH=backend:.
trial() {
  backend/.venv/bin/python -m scripts.course_trial "$@" --topic "$TOPIC" --offline-vault "$VAULT"
}
trial inspect > "$INITIAL_APPROVAL"
trial prepare --owner "$OWNER" --approval "$INITIAL_APPROVAL"
trial send --mock-response "$FIRST_DRAFT_RESPONSE"
trial replay
```

审核者根据 `generate.candidate.json` 写入 `review.json`。意见包含 `candidate_digest`、`verdict: needs_revision`、非空 `independent_evaluator`、`full_lesson_reviewed: true`、相同的 `findings` 和 `blocking_findings`。每项注明 `path`、`quote`、`area`（`citation` 或 `teaching_expression`）、`severity: minor`、`repairable: true`、`issue` 和 `teaching_responsibility`。头插还使用原父稿、规划依据及教学证据绑定字段。

准确修订记录包含 `version: shared-trial-limited-revision-v1`、`topic`、`batch`、`parent_digest`、`review_sha256`、`allowed_paths`、`max_http_requests`、`offline_fixture: true`、`approved` 和 `request_sha256`。审核摘要为规范 JSON 的 SHA-256。路径列表须与审核逐项一致。预览阶段可用 `approved: false` 与 `request_sha256: null`。准备时记录必须批准一次请求，并写入预览得到的准确请求摘要。

```sh
trial inspect-revision --record "$REVISION_RECORD"
trial prepare-revision --record "$REVISION_RECORD"
trial send --stage revise --mock-response "$REVISION_RESPONSE"
trial replay --stage revise
trial publish --stage revise
# 需要终止时执行
trial stop
```

`publish` 前将完整重评写入 `revision-review.json`。重评必须绑定子稿及父稿摘要，明确 `full_lesson_reviewed: true`，通过主题原有检查项并清空阻断意见。课程投影显示父子关系和 `offline_fixture` 来源。T126 只接通离线调用，真实 Provider 授权为 0。复核 T125 的原清单时使用其冻结提交 `27966c5`。

## 验证记录

后端 24 项、播放器与状态 16 项通过。前端类型检查、定向 Ruff、项目工作流及 Git 差异检查通过。离线清单 SHA-256 为 `8774b0abb993967b8d6bdfa7e698322f78dc0e4bb332ddd434e15f85d2ac40a8`。[清单](manifest.json)

| 检查 | 结果 |
| --- | --- |
| 四主题允许范围 | 拒绝题干、解析、帧说明、代码、状态、答案、越界和重复路径。拒绝重大意见与非头插的 `failure_scope`。 |
| 两个独立父稿 | 头插生成仅含 `paragraph_1_fact_ids`、`failure_scope` 的 Schema，栈生成仅含 `paragraph_0_text`、`summary` 的 Schema。共用 CLI 完成预览、准备、Mock 发送、重放和准入。 |
| 绑定和预算 | 拒绝错父稿、错审核摘要、发送前调换审核、超范围审批、无批准、零预算、超额预算、错请求摘要及重复发送。直接调用真实发送路径被拒。 |
| 原件和重评 | 拒绝越界响应、缺解析首稿、用父稿审核准入以及未完成全文重评。比对合并结果、原件字节、计划及材料摘要。子稿通过测试重评后在专用 PostgreSQL 中准入，练习答案及解析仍为私有字段。 |
| 现有播放器 | 从实际准入投影读取头插 13 帧和栈 5 帧，验证帧说明、高亮、前后步、重置和父稿摘要。 |

复现时用既有 `scripts.run_catalog_db_tests.test_environment` 为专用库注入连接，运行 Alembic 至 `0050`。设置 `EDUMIND_T126_PLAYER_PROJECTIONS=/tmp/edumind-t126-player`，并先创建该输出目录。

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q \
  backend/tests/test_shared_course_trial_revision.py \
  backend/tests/test_head_course_reuse.py::test_dynamic_revision_text_citations_and_materials_immutable \
  backend/tests/test_head_course_reuse.py::test_review_scope_refuses_drift \
  backend/tests/test_course_question_stem.py --tb=short
EDUMIND_T126_PLAYER_PROJECTIONS=/tmp/edumind-t126-player pnpm --dir web exec vitest run \
  tests/course-visualization.spec.ts tests/head-course-status.spec.ts
pnpm --dir web typecheck
```
