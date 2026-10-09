# T036 隔离队列验收

T036通过已批准ADR-0009及Phase1验收计划的队列/模板兼容验收。真实Provider请求0；默认catalog_only及既有人工签核目录继续有效。本验收不批准动态入口、部署或新课程。

源码基线`125dec6d070847d8201684e6cde0e403268d0d78`，各协议固定当前源码字节、backend锁文件、模板与签核目录。使用新专用PG数据库、既有专用测试Redis、生产Celery消费者/派发器/独立宿主控制器、实际隔离Manim容器和Chromium。PG/Redis实际镜像摘要见results/runtime-images.json；Manim固定89ab433c…，实际容器运行由既有渲染器安全限制。硬件Apple M3/8逻辑核/16GiB、macOS15.6.1 arm64，串行渲染。四组证据均原样保留，结果/index摘要绑定，不覆盖失败记录。

| 分组 | 实际命令 | 结果及原始证据 |
| --- | --- | --- |
| 恢复契约 | `backend/.venv/bin/python scripts/run_phase1_queue_acceptance.py --run-id r01` | 55通过、0失败/跳过；local-materials/phase-1-t036/r01/fault-tests.xml及log。真实solo父进程/prefork子进程死亡、Redis重启、迟到容器二次清理/RPC确认丢失10秒清理；单元PG注入与真实进程测试分别保留。 |
| 模板与SSE | `backend/.venv/bin/python scripts/run_phase1_queue_matrix.py --run-id r02` | 100/100模板，各模板50；新私有缓存20未命中P95=9.522318s≤90s，另外80命中0渲染。每槽实际HTTP授权导出MP4/SRT、Chromium解码播放和规划指针步骤检查。100/100实际断线恢复，Job50/课堂50。 |
| 故障窗口 | `backend/.venv/bin/python scripts/run_phase1_queue_fault_matrix.py --run-id r01` | 7/7：API202后发送前死亡、真实lateACK前后死亡及重复、Worker实际PG隧道断连、真实兼容PG/Celery回退、notes/跨owner导出、实际签核目录运行中撤回。DB断连旧容器清理0.82828s，恢复attempt2/单正式绑定。 |
| 发送后宕机 | `backend/.venv/bin/python scripts/run_phase1_queue_publish_fault.py --run-id r01` | 真实Redis发送后、PG回执提交前杀死本次发布者，等待实际30秒租约过期产生至少2真实投递；正式渲染attempt1/一个owner绑定，不伪造DB时间。 |

矩阵结果见results/template-sse-matrix.json。Job连接实际关闭后使用持久游标重连，包含20API重启、20终态重放及10过期游标410→快照→重新订阅；不把单独拒绝算成功。课堂POST流在message_ready证明事务发布后关闭，按原幂等键重放，包含25API重启/25终态；消息与operation保持一致，不增加模型生成调用。课堂使用明确本地MockProvider，只验证HTTP/PG持久化重放，不声称真实模型质量或生成中断前提交恢复。API仅localhost自签TLS，Secure会话Cookie仅在运行内存，不记录凭据。

ACK边界钩子只暂停测试消费者的真实Celery Request.acknowledge；正式消费、租约、渲染、发布均使用产品实现。DB故障仅断开该Worker专用字节隧道，不停止共享测试PG。课程撤回最后执行，仅修改新测试DB中的批准目录副本；不改原人工签核或开发数据。无flushdb或任意业务队列清空；消息丢失使用现有专用队列的固定消息LPOP契约，ACL拒绝flushdb/越权前缀已验证。

补充命令`backend/.venv/bin/python backend/tests/queue_media_frames.py local-materials/phase-1-t036/matrix-r02`提取实际插入/删除中间帧，已自查先保存后继、连接前驱、重新连接和最终状态；位于matrix-r02/*-frame-*.png。不把AI自查当新人工签核。原签核课程/模板规则保持不变；T037另有DSL人工验收。

首轮matrix-r01在API健康探测失败，100模板/100SSE均未执行，P95=+inf；原结果保留results/prior-api-start-failure.json，未计为通过。补充localhost探测诊断、禁环境代理和子进程无缓冲后，独立新DB完整r02通过；没有证据断言原失败唯一根因。证据汇总初次路径名不匹配/沙箱不许读sysctl均失败留在执行记录，纠正路径并通过工具审批读取硬件后完成汇总，不影响原矩阵。

`backend/.venv/bin/python scripts/verify_phase1_queue_evidence.py`验证固定源码/原结果摘要、分母、P95和故障组并生成一次性完整证据，不覆盖已有汇总。Ruff/格式、任务治理、旧历史原件校验、diff自查通过。真实模型、课堂质量、DSL媒体安全、动态恢复和阶段整体验收均不由本项代替。
