# T120 共用课程试验入口验收

2026-11-10，在同一隔离 PostgreSQL、开发应用和 Chromium 访客会话中，两份历史候选均准入私有 v2。应用入口为 [本机课程列表](http://127.0.0.1:5213/)，从交接窗口的「继续学习」打开对应课程。[验收明细](verification.json)

| 主题 | 封存来源与规划 | 浏览器验收 |
| --- | --- | --- |
| T118 空链表头插 | 原模型规划与已授权的单叶引用修订。父稿及原拒绝和 STOP 仍在 r02 封存目录 | 13 个阅读块、13 帧、高亮及播放控制。四题反馈 0% / 100%，刷新恢复作答和原 v2 |
| T119 栈 | 程序固定提纲与已审首稿 | 6 个阅读块、5 帧、高亮及播放控制。四题反馈 0% / 100%，刷新恢复作答和原 v2 |

两课的详情页标明「历史封存回放」，并显示原批次、规划来源、候选与父稿身份。服务端读取在提交前隐藏答案及解析，另一访客读取场景和作答返回 404。每课两次作答 POST，刷新新增 0 次。数据库中两课各有一条回放结果，生成尝试和调度尝试都是 0，回放的用量字段为空。Provider 调用和新模型成功均为 0。

## 重构边界

- 三个历史前台调用路径共用 `scripts/course_trial_transport.py`，复用既有 DNS 固定、SNI、精确请求字节和加密原件收集。各批的授权、限额、阶段顺序和收据形状继续由原入口约束。
- `scripts/course_trial.py` 以主题选择原封存读取器。头插在 `655d25b`，栈在 `d1d4c2d` 的临时 Git 归档运行原读取器并核对全部冻结文件，随后由 `course_trial_sources.py` 复核实际请求、响应、候选及审核摘要。头插调用原有限修订和十二项审核校验，栈调用原首稿绑定及七项审核校验。
- `course_trial_replay.py` 使用同一私有准入事务保存两课，复用仓储、围栏、场景机械准入、版本提交和答题服务。新增读取投影的回放来源分支，沿用数据库的回放来源及零尝试约束。[契约补充](../../ADR/0060-sealed-course-trial-replay.md)
- 此入口的两个动作是 `replay` 和 `publish`。当前任务的实际执行范围是封存复核与开发私有准入。新批前台请求仍需单独冻结和授权，历史发送窗口已经结束。

## 复核命令与结果

```sh
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_head_course_goal_dev.py --profile trial-replay --prepare --start
PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.course_trial replay --topic head
PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.course_trial replay --topic stack
PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.check_course_trial_replay
```

验收脚本以同一浏览器访客调用两次 `publish --topic <head|stack> --owner <UUID>`，并对每课再执行一次验证幂等。跨主题候选双向、错候选审核双向、头插未授权修订、栈额外父稿及跨主题材料共 7 个反例均被拒绝，未新增课程记录。回放前后 43 个历史封存文件的摘要一致，覆盖 T118 r02 的失败及 STOP。历史冻结包和两主题材料文件经 Git 差异核对一致。

定向 Python 测试 32 项通过，包括共享传输 MockTransport、严格回执、主题材料和修订边界。原窗口的 3 项前台集成测试未在重构工作树运行，本轮以原提交严格重放及真实隔离库准入替代旧窗口路径。前端 12 项、类型检查、Ruff 和任务工作流通过。ESLint 有 4 条既有模板换行警告，浏览器无页面错误。

## 接入第三主题

1. 新增该主题的材料模块和冻结包，提供目标、规划来源、代码、轨迹、事实、题目和私有答案。为候选定义该主题的审核项及有限修订边界。
2. 在 `backend/app/services/course_trial_sources.py` 注册准确来源摘要与审核适配。在 `scripts/course_trial.py` 增加相应封存读取器分支。复用传输与封存模块以及共用私有准入事务。
3. 在 `backend/app/contracts/free_course.openapi.json`、`web/src/api/freeCourses.ts` 和 `CourseWorkspace.vue` 增加主题来源值及标签。只有轨迹需要新的展示结构时才接线 `CoursePresentation.vue`。
4. 在 `scripts/check_course_trial_replay.py` 添加新主题的独立参考断言及浏览器验收，保留跨主题和修订越界的拒绝检查。
