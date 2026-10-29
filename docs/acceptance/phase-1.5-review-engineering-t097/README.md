# T097：隔离审核工程修复

[新隔离适配器](../../../scripts/isolated_diagnostics/p15_review_engineering.py)统一使用不可变 `ReviewPolicy`：请求和响应各最多 65,536 字节，输入预约/上游回报检查为 32,768 token，输出预约/请求及检查为 8,000 token。`ReviewAttempt` 使用同一配置生成请求、登记预约并验证响应；状态单次封闭。字节数不能换算成可靠 token 数，**发送前实际 token 数尚无可信计数保证**；上游用量超出预约仍拒绝，不代表上游实际硬限。

对 T095 的真实候选离线重建审核请求：原 79,305 字节，新 **59,507 字节**。保留完整原始与展示产物、代码、答案、全部动作与参考，181 个审核目标逐一保留 ID、路径和精确文本；仅移除目标表中可由本地重建的类型、值摘要等元数据。原完整 `make_binding` 仍用于本地候选与精确 quote 校验。精简可能影响模型行为，离线大小/引用检查不能证明模型遵循或教学质量。

审核 reasoning 中非空 `encrypted_content` 仅在 review 的私有校验视图中按字符串上限 8,192 字符隔离，不解密、不用于判定或转发；原响应不变，原模型、来源、JSON、其他字段、引用和未知项门禁保留。原 T096 自报 32,786 输入仍超过新 32,768 限额，**不追认其协议通过**。新隔离是对指定字段的兼容行为，不代表提供商真实身份或完整上下文已验证；未接生产网关，也未授权真实调用。

`stopped_summary` 对已停止批次只读重放已记录请求和响应，不调用 `next_request()`；已实际重放 T095 47 事件，得到 9 次发送与验证、下一状态审核未发送，并拒绝额外未绑定文件和原始响应篡改。旧执行器及原始包不修改；新汇总是隔离工具，不能将旧批次改为成功。

验证：`PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_review_engineering.py scripts/tests/test_p15_combined_candidate_contract.py scripts/tests/test_p15_bound_pilot.py scripts/tests/test_p15_minimal_contract.py -q --tb=short`，**159 passed / 0 skipped**。覆盖真实候选全 181 目标、字符串及对象投影、引用路径、错候选/引用/未知字段/加密内容边界、预算超限、单次封闭、旧失败重放及额外文件/原件篡改。Ruff 与严格 mypy、工作流及 `git diff --check` 均通过。零真实调用。
