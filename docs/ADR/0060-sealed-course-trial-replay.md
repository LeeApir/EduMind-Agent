# ADR0060 封存课程试验回放

T120 在隔离数据库 `edumind_catalog_p15_t120_replay` 使用一个主题选择入口，准入两份经独立审核的历史候选。新投影沿用 `replay_source`，新增闭合分支 `sealed-course-trial-replay-v1`。分支标明原批次、主题、规划类型、原首稿或授权修订、候选与父稿、计划与材料摘要以及 `new_provider_calls: 0`。既有回放投影仍可读取。

写入沿用私有仓储及已有回放来源 `existing_real_candidate_replay`。生成结果记录零次尝试和空用量，练习答案继续保存在服务端。按原 Git 提交运行历史读取器，核对准确请求和封存响应。T118 需复核原批准、唯一引用叶及全文审核，T119 需复核固定提纲、首稿和主题审核。原封存失败与 STOP 保留。开发应用沿用现有阅读、播放和反馈界面。

本次准入限于这两个固定归档和本机隔离应用，授权范围为零 Provider 调用。[统一验收记录](../acceptance/phase-1.5-course-trial-replay-t120/RESULTS.md)
