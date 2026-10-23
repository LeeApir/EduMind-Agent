# T049 真实课程创建画像快照修复

T037诊断组装发现Scheduler.enqueue遗漏画像，真实API始终产生null画像。现按已批准有据画像请求契约，在owner锁内首次选择同owner最高version画像；相同创建收据则复用原request的profile_id，画像更正不会改变幂等请求摘要或重放。旧null快照重放仍null，其他owner画像不参与。公开API字段、产品模式、签核与正式掌握度均不改变，无迁移或Provider调用。

实际命令：`backend/.venv/bin/python docs/acceptance/phase-1.5-profile-create-t049/run_checks.py --run-id r01 --output /tmp/edumind-p15-t049-r01`，4新隔离PG实际HTTP/API/调度/快照共92通过、0失败/skip。新增2项覆盖最高版本选择、真实规划Prompt读取原快照、画像更正后重放、变更目标冲突、无画像/跨owner与旧null重放；原API7、调度39、快照44保持。Ruff相关服务和新测试、严格mypy该服务、工作流/diff通过；实际raw log/XML SHA和库名见results.json。

不把自述当掌握度，不用诊断夹具另注画像绕过真实API；Provider0、生产catalog_only、H封存及用户原文件保持。独立完成提交后恢复T037，使用修复后的真实入口冻结诊断包。
