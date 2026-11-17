# T125 四主题共用首稿入口

`scripts.course_trial --new-batch` 选择本批的四个首稿配置。空链表头插使用现有模型规划线格式、规划持久化和独立规划审核。栈、队列和二分查找使用各自的程序固定提纲。正文均由原主题构造器显式选择 `course-question-stem-v2`，沿用各自的 Schema、材料和教学审核项。新准入投影记录 `generation_source`、规划来源和题干提示词版本，原封存导入仍使用 `replay_source`。

| `--topic` | 批次 | 规划来源 | 规划／正文请求上限 | 演示帧 |
| --- | --- | --- | --- | --- |
| `head` | `head-stem-v2-r01` | `model_planned` | 1／1 | 13 |
| `stack` | `stack-stem-v2-r01` | `fixed_outline` | 0／1 | 5 |
| `queue` | `queue-stem-v2-r01` | `fixed_outline` | 0／1 | 5 |
| `binary-search` | `binary-search-stem-v2-r01` | `fixed_outline` | 0／1 | 6 |

## 命令

从仓库根运行。`inspect` 只读，输出批次、规划来源、提示词版本、清单摘要和请求上限。固定提纲正文的请求摘要在清单内。头插正文的准确请求依赖该操作的规划结果，按请求原件和摘要封存。

本轮核验的 [manifest.json](manifest.json) SHA-256 为 `635449784eb8095a47c14dd56ed9baaf46526ffca3721b8e16c15fe9541645f4`。

```sh
export PYTHONPATH=backend:.
backend/.venv/bin/python -m scripts.course_trial inspect --new-batch --topic head
backend/.venv/bin/python -m scripts.course_trial prepare --new-batch --topic "$TOPIC" --owner "$OWNER" --approval "$APPROVAL"
```

`prepare` 检查准确批准，创建专用库 `edumind_catalog_p15_t125_trials` 中的新操作及本机私有原件目录 `~/.local/share/edumind/<批次>`。本次交付的真实请求授权为 0。真实发送另需对应清单、主题、批次和版本的批准，沿用原前台 1,800 秒窗口、隐藏输入和 C2 停止及费用边界。批准字段由 `course_trial_generation.approval_values` 定义，测试批准带 `offline_fixture=true`，只能用于测试路径。

头插在正文前执行以下规划步骤：

```sh
backend/.venv/bin/python -m scripts.course_trial send --new-batch --topic head --stage plan
backend/.venv/bin/python -m scripts.course_trial replay --new-batch --topic head --stage plan
```

独立审核者根据 `plan.candidate.json` 出具 `plan-review.json`，绑定 `candidate_digest`、`plan_digest` 和 `payload.planning_basis.binding`，使用原空链表规划审核项。正文审核写入 `review.json`，绑定 `generate.candidate.json` 的摘要。头插还核对父候选为空、规划依据和教学证据摘要，四主题分别保留原有的检查项与阻断意见要求。

```sh
backend/.venv/bin/python -m scripts.course_trial send --new-batch --topic "$TOPIC"
backend/.venv/bin/python -m scripts.course_trial replay --new-batch --topic "$TOPIC"
backend/.venv/bin/python -m scripts.course_trial publish --new-batch --topic "$TOPIC"
backend/.venv/bin/python -m scripts.course_trial stop --new-batch --topic "$TOPIC"
```

`stop` 写入 `HALT` 并请求数据库取消。现有 `STOP` 保留请求已消费或失败的原始含义。已封存的成功候选仍可只读重放，停止后拒绝发送和准入。省略 `--new-batch` 的历史重放按原冻结提交运行。

## 离线验证记录

专用容器 `edumind-phase1-t037-pg` 的隔离库 `edumind_catalog_p15_t125_trials_test` 实际迁移至 `0050`。后端按以下命令运行，专用库 URL 由既有 `scripts.run_catalog_db_tests.test_environment` 注入。`EDUMIND_T125_PLAYER_PROJECTIONS=/tmp/edumind-t125-player` 将实际 API 读取到的四份私有场景投影交给播放器测试。

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q \
  backend/tests/test_shared_course_trial.py \
  backend/tests/test_course_question_stem.py \
  backend/tests/test_course_trial_transport.py --tb=short
EDUMIND_T125_PLAYER_PROJECTIONS=/tmp/edumind-t125-player pnpm --dir web exec vitest run \
  tests/course-visualization.spec.ts tests/head-course-status.spec.ts
pnpm --dir web typecheck
```

| 检查 | 实际结果 |
| --- | --- |
| MockTransport、隔离库、私有 API | 20 项通过。四主题逐一比对发送字节与封存请求、原主题 Schema 和材料。头插完成一次规划及一次正文，其他主题各一次正文。逐一拒绝错主题、旧批准、缺少或错配审核、重复发送和停止后准入。准入后读取 v2，来源与候选摘要一致，答案和解析仍为私有数据。 |
| 现有播放器 | 18 项通过，含实际准入投影的 13／5／5／6 帧、代码行高亮、帧说明、前后步和重置。类型检查通过。 |
| 历史重放 | 头插、栈、队列首稿、队列修订和二分查找修订使用各自冻结提交重放。历史二分首稿仍被 `SAVED_BINDING` 拒绝。队列首稿能机械重放，其原教学拒绝保持在旧记录中。 |
| 静态与工作流 | 四主题 `inspect`、定向 Ruff、工作流与 diff 检查通过。旧头插入口的 8 项历史 Ruff 诊断逐项比对一致。 |

本轮 Provider 调用 0。Mock 正文和审核仅用于验证首稿接线与私有准入。后续真实批次需另行取得准确执行授权。
