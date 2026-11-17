# ADR-0051：头插真实候选的开发环境主链回放

- 状态：Proposed，未批准、未实施产品接线。
- 日期：2026-11-03。
- 任务：PHASE-1.5-T107。
- 前置：T106 已完成；该批 STOP 不解除，新增 Provider 请求 0。

用户授权的是复用既有真实候选、私有草稿和现有课程组件完成最小接线，并要求不能无损表达的部分集中提出契约变更。本提案处理实际核对出的必要差异；不把实现方向授权代填为具体 API、持久化或教学动作契约批准。

| 决定 | 具体变更 | 旧行为与边界 |
| --- | --- | --- |
| A 回放来源与入库 | 仅开发专用数据库、本机显式 CLI 导入固定 C01 首版/C02 修复版。新增场景候选 `origin_type`：旧记录默认 `model_generation`、`sent_attempts=1`；回放必须 `existing_real_candidate_replay`、`sent_attempts=0`、`usage_json=null`。只追加 Alembic 迁移，约束两者配对。原文件 UTF-8 字节、摘要、父稿、映射版本及完整 fact 绑定存私有候选 input_snapshot；response_json 是映射候选，不能冒充模型原始响应。 | 复用候选/准入/展示/ready/版本清单及 owner 围栏，不增加导入 HTTP 权限、生成调度器或外部调用。现有表强制 sent_attempts=1，不能伪造一次新生成来入库。 |
| B 同步状态与行定位 | 新显式可视化类型 `head_insertion_replay_v1`，每步含严格 `head_frame`：原 frame_id/state_index/fact_id/kind/line、模型原 title/note、准确原 state、code_anchor 和派生 locals_scope。同一游标原子选择讲解/状态/高亮行，复用 `show_step`、CoursePresentation、CourseWorkspace；补齐同一游标的播放/暂停/前后步/重置。 | 不修改旧 VisualStep、旧四种可视化或旧动作含义，不扩通用执行器。旧客户端不认识新类型时显示演示不可用，不能画成空链表。原状态的 NULL 与 indeterminate 原值保留；initial/caller 为局部不在作用域，其余为函数局部检查点，历史局部值只作快照。 |
| C 类型化练习比较 | 公共 Question.input_type 及对应回放私有题允许 `json_integer_array`、`integer`；旧 `short_text` 保持原比较规则。提交载荷仍为 answer 字符串。服务端对新类型严格解析 JSON：数组只容许有序整数，排除 bool/浮点/嵌套/非数组；integer 只容许整数，排除 bool/浮点。按类型比较，JSON 空白不影响；格式错误视为完整提交中的不匹配并给固定格式提示，仍保存原作答。 | Answers/服务端私有 answer_key 与 solution、整组完整后反馈、provisional/course_only、owner/幂等/版本身份保持。新题型规则须持久绑定题组 rule_version；旧题组不重评、不重算旧记录。前端不下载题库答案，不采用独立 HTML 的浏览器答案。 |
| D 来源投影与开发运行 | SceneProjection 增可选严格 replay_source（仅声明既有真实候选回放、T106、slot、候选 digest/文件 SHA、parent、model/prompt/mapping version）。页面显示来源与未签核；单个场景承载完整课程，创建一套固定不可变版本清单。导入命令只接受固定 case 和已存在 owner，拒绝非专用数据库；依 owner+候选摘要幂等，同候选再次导入不换 head、不重复写。 | 不扩公开草稿或管理员分享权限，不把评估 pass 转成产品正式签核/掌握度。正常模型 Schema/Prompt/预算及原 T106 材料不改。开发实例允许 dynamic 以使用现有练习入口，但必须加本机禁出站与拒绝 Provider 的运行配置，生产默认 catalog_only 不变；无真实 Provider 或部署授权。 |

准确附件见 [T107 审查包](../acceptance/phase-1.5-head-replay-t107/README.md) 与 [manifest](../acceptance/phase-1.5-head-replay-t107/manifest.json)。其中 Schema、两个公共投影及私有保存映射均为离线提案，UUID 是标明的演示身份，不是数据库中已存在课程。

实现应扩展现有准入与展示的显式回放分支：普通模型生成分支仍走原请求/Schema校验；回放分支必须按固定来源重新计算并逐值验证映射，不以 `origin_type` 自述绕过硬门。通过后复用同一 FreeSceneValidation、FreeScenePresentation、FreeCourseStep 和课程版本事务，不手写一个虚假模型 success。未知来源、串 owner、错误行/帧/父稿或丢字段必须拒绝并保留失败记录。

验收仍要求真实 PG、实际 ASGI 应用与现有 Vue 课程页：两例全帧/行/作用域、四题错误及正确输入、服务端反馈、重置和刷新、跨 owner 不可读、旧版本不能串评分、原件摘要不变、Provider 计数 0。离线样例不能代替这些检查。实现完成交评估，不自动扩大样例或开启后续生成；T102 保持 blocked。

请一次审查 A—D 及准确附件。获准后在同一 T107 继续实施；当前不登记 T107 完成，不声称已有应用入口。
