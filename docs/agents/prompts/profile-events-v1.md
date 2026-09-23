# Progressive profile event & merge rule v1

版本：`profile-merge-v1`。事件 schema 由 `backend/app/agents/profile_events.py` 定义，合并与显式修正规则由 `backend/app/agents/profile_schema.py` 定义。本文件是二者的可读说明，代码校验才是唯一执行边界。

## 事件 schema

`ProfileEventRequest` 只接受白名单行为摘要，客户端不能写入得分、掌握状态或画像字段。必填 `event_type` 与 `knowledge_node_id`，可选 `learning_unit_id`、`scene_id`、`action`：

| event_type | 允许的 action |
|---|---|
| `hint_used` | `hint_level_1`、`hint_level_2` |
| `reexplanation_requested` | `simpler`、`deeper`、`different_example` |
| `resource_selected` | `code`、`exercise` |
| `explicit_feedback` | `too_easy`、`too_hard`、`liked_explanation`、`skip`、`mark_known` |

`action` 属于某一 event_type 时，禁止用于其他类型；`knowledge_node_id` 必须匹配 `^[a-z][a-z0-9-]{1,63}$`，`learning_unit_id`/`scene_id` 匹配 `^[A-Za-z0-9_-]{8,64}$`。测验作答必须走专用测验提交端点，不属于本事件。

## 证据与画像版本

每个非空画像维度都携带证据记录，字段固定为 `source`、`confidence`、`observed_at`、`profile_version`。`source` 只允许 `initial_query`、`learner_statement`、`learning_behavior`、`explicit_feedback`、`manual_correction`。`confidence` 是这条证据对字段的支持程度（0–1），不是能力评价。未知字段保持 `null`，不创建证据。证据的 `profile_version` 可以小于等于当前画像版本，从而把旧证据无损带入新快照；不能大于当前版本。

## 合并优先级

证据来源按强度固定排序（强到弱）：`manual_correction` > `explicit_feedback` > `learner_statement` > `learning_behavior` > `initial_query`。一个字段的主导来源取其证据中最强者；`manual_correction` 一旦出现即覆盖任何模型推断。冲突规则是确定性的，不依赖时间或 Provider。

## 手动修正

只有 `professional_background`、`learning_goals`、`error_preferences`、`engineering_preference` 四个维度允许学生修改。每次有效修正在原快照基础上创建新版本：覆盖被修改字段，追加一条 `manual_correction` 证据（`confidence` 为 1.0、`observed_at` 为修正时间、`profile_version` 为新版本），其余字段与旧证据原样保留。不得就地改写历史快照。
