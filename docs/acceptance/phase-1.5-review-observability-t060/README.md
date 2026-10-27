# T060 隔离审核可观测性修复交接

ADR0038 A—B 已获用户明确“批准”，[登记](../../ADR/0038-approval-20261027.json)绑定06ac4f9提案manifest。冻结ADR/附件保留原字节，以登记为当前接受状态。

新增 `scripts/isolated_diagnostics/p15_review_observability.py`：缺失/null instructions明确echo_unavailable；存在但漂移仍拒绝。仅允许至多一项精确summary_text结构、≤4096字符，content仍须空，不透明密文≤262144且不解密；摘要只核对形状与长度，不解释、展示或转发。结果始终 instruction_delivery_verified=false / upstream_context_verified=false / production_admission=false。

实现通过私有验证视图复用原完整内容校验，原响应不改、不保存该视图、不伪造回显。新adapter核对准确请求input与原source envelope，并绑定规范wire字典SHA。原Schema、来源、准确引用、用量与推理包含关系、最终消息/工具拒绝继续生效。模块无传输能力；尚未接线真实执行器，未来接线还须记录安全观测字段并冻结准确新包，旧r04仍使用旧规则。

实际验证：

- `backend/.venv/bin/python -m pytest scripts/tests/test_p15_review_observability.py scripts/tests/test_p15_sol_compatibility_proposal.py scripts/tests/test_p15_full_r04_results.py -q --junitxml=/tmp/edumind-t060-unit.xml`：107 passed / 0skip（新61、旧34、结果12）。首次probe夹具漏原Schema必需review_version被正确拒绝；补完整夹具后通过，原Schema未改。
- `python3 /tmp/edumind-offline-0038-pg.py t060 backend/tests/test_p15_review_observability_pg.py`：2 passed / 0skip。可复现脚本见本目录run_pg_offline.py，专用新库edumind_catalog_p15_t020_t060_offline；只有数据库socket允许，HTTPX Mock。成功路径保持生产拒绝；错误source SHA保留unknown且再次执行不发请求。
- 新三文件Ruff通过；工作流检查和diff检查通过。自查完成，未宣称独立评审。
- [只读回放](replay.json)：准确r04原始请求/响应按新规则校验，旧规则仍报UNRECOGNIZED_INSTRUCTION_ECHO，原始文件及ledger SHA保持。没有重结算或追认原批次实际通过；最终JSON pass不是教学质量结论。

新增真实调用0，无生产网关/课程Prompt/输出Schema修改；T038继续blocked、r04 unknown保留。下一任务T061仅离线版本化唯一答案域与输入格式，独立完成提交。无关用户修改未纳入。
