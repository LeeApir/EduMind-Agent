# ADR-0028：owner私有记录索引与掌握度来源读取

状态：Proposed，待用户准确批准。仅补齐已批准T031/T032的读取前置，不新增产品范围、持久化表、写权限或真实调用。

## 问题与证据

T020/T045提供按已知ID读取作答、反馈、导师及操作；无持久记录索引。`GET /api/mastery`只返回当前分数/版本/简短摘要，没有revision来源、`recomputed_from`或撤销作答引用。T019已有全部私有事实及同owner约束，但浏览器sessionStorage不是完整账本。T031要求撤销/重算追溯，T032要求真实练习/修订记录恢复，不能以本机缓存代替。

## 待批准 A—C

| 项 | 准确取舍 |
| --- | --- |
| A 记录索引 | 新增按course、kind分页的只读GET，返回owner已有记录ID和时间，正文沿既有单条GET最新投影读取。缺失或外域course/cursor统一404，无批量正文或缓存答案。 |
| B 掌握度来源 | 新增按node分页的owner历史revision GET，返回旧分数快照、规则、准确重算前一revision及来源引用。新作答/撤销可追到准确旧attempt；旧来源只给既有资源引用，不开放任意原始payload。当前有效性继续以当前掌握度和作答GET为准。 |
| C 安全与交付 | 只读/no-store/已有会话；owner锁定所有连接和cursor；不加维护写接口、不返回私有答案、核定原文/Prompt/配置/密钥。无新迁移/生成/开放；先做实际隔离PG/HTTP验收，再实施T031/T032页面。 |

准确字段、分页、降级和测试要求见[契约](../acceptance/phase-1.5-record-read-contract-r01/contract.md)与[OpenAPI](../api/phase-1.5-record-read.proposed.openapi.json)，由[manifest](../acceptance/phase-1.5-record-read-contract-r01/manifest.json)固定字节。批准前不实现新路由、不将planned并入runtime契约。

本提案不重启真实Provider或计费、dynamic、部署、H测试或旧质量/性能验收。原ADR0024–0027与准确附件保持原字节。T046保存设计与批准门禁，T047/T048分别实现两个可独立验收的读取行为；两项完成后再做T031/T032。
