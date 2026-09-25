# Progressive profile behavior prompt v1

版本：`profile-behavior-v1`，实现位于 `backend/app/agents/profile_agent.py` 和 `backend/app/services/profile_behavior_updates.py`。

画像更新在学习证据提交后单独执行。Provider 只接收事件类型、知识节点和最小行为摘要：测验得分与预定义错误模式，或提示、重新解释、显式反馈的动作；资源偏好只接收 `code`/`exercise` 选择。不发送原始作答、题目、提示正文、完整画像、用户初始目标或身份信息。

输出仅为 `updates` 字段增量。测验、提示、重新解释和显式反馈最多提议 `error_preferences`；资源选择最多提议 `engineering_preference`。证据来源、置信度、时间和画像版本由服务端赋值，Provider 不可自行提供。证据不足返回空增量，其他未知画像维度保持 `null`。

服务端按 `profile-merge-v1` 合并证据并保存不可变新版本，同一证据只生成一个版本；手动修正优先级最高。Provider 不可用、输出越界或校验失败时不生成新画像，已提交的学习证据不回滚。接口回执通过 `profile_update_status` 报告 `updated`、`no_change`、`provider_failed` 或 `conflict`。
