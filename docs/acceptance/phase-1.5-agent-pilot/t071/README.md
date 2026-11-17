# T071 全批状态与真实事件时间验真

用户准确批准d82cb8e中的限定离线前置任务；批准记录approval.json。本轮无Provider、Key、生产API/评分/部署授权。

## 实现与界限

p15_pilot_batch.py是无IO的纯批次Reducer。初始状态由准确grant/inputs/package构造，按事件顺序推导当前槽/臂、唯一在途调用、预约/发送/可信结算、独立检查点、当前位置和不可逆停止。它不重做教学语义判断；原有角色Schema、逐槽完整请求/FSM重演、独立报告所有版本的事实/答案/代码/动作/教学核验继续保留。

Journal.record在SQLite事务中核对旧摘要链和batch/calls投影，先验证拟追加事件，再原子写入事件及派生状态；不再靠手工advance/update维护实际运行状态。guard同样核验投影。预约、发送、可信结算、正常成功/本地拒绝结果及独立accept的记录epoch须在准确[start,deadline)内且不得回退；含等待，不延长窗口。停止事件和已发送调用的迟到原件只作证据，不能新预约、结算成功或推进。

窗口外或时钟回退的已有候选保存为late_slot_result，并保持stopped、当前位置和零成功分子，不打开新的独立审核检查点。wire_observed可记录已发送调用的迟到原始响应；既有unknown不会退款或重发。检查器用相同Reducer重演全批，并要求最终SQLite批次和逐调用状态完全相符，再进行原有完整wire/结果/独立报告核验；逐槽Replay的合成时钟不再充当全批真实时间证据。

窗口核验验证的是记录时间与批准窗口的一致性；同一用户/文件系统的本机时钟与摘要链不是外部可信时钟或密码学身份认证。输出明确clock_source_independently_attested=false。无实际模型调用，不能据此宣称模型兼容、教学正确、费用或正式T069/T070通过。

## 独立期望与验证

独立助手在未读取新Reducer前手写fixture：scripts/tests/fixtures/p15_pilot_batch_manual.json，38例（8正/30反），哈希和假设见independent-fixture-notes.md。测试只展开指定事件，核对手写状态与准确拒绝点，不用Reducer生成期望。

新增11项发送端/只读集成验证覆盖：同时重算摘要链后超窗reserve/sent/settle/assistant accept/普通结果，下一臂在accept前出站，独立stop后拼接后续有效槽，直接record绕过检查点，迟到候选不计成功，临界时钟预约原子回滚，以及SQL状态与事件不一致。旧64项wire/授权/逐槽回归保留。

```
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_pilot_batch.py scripts/tests/test_p15_pilot_wire_execution.py -q --junitxml=/tmp/edumind-p15-t071-integration.xml
MYPYPATH=backend:. backend/.venv/bin/mypy --strict --explicit-package-bases --follow-imports=silent scripts/isolated_diagnostics/p15_pilot_batch.py scripts/isolated_diagnostics/p15_pilot_execution.py scripts/check_p15_pilot_execution.py scripts/isolated_diagnostics/p15_pilot_replay.py
backend/.venv/bin/ruff check scripts/isolated_diagnostics/p15_pilot_batch.py scripts/isolated_diagnostics/p15_pilot_execution.py scripts/check_p15_pilot_execution.py scripts/isolated_diagnostics/p15_pilot_replay.py scripts/tests/test_p15_pilot_batch.py scripts/tests/test_p15_pilot_wire_execution.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

实现期上述测试113 passed/0skip，mypy4源/Ruff通过。首次集成发现旧timeout夹具直接修改已冻结窗口，已改为从独立短窗口grant启动；原预算/unknown/不重发断言保留。伪造报告身份测试现在由更早的共享批次身份门禁拒绝，断言相应精确错误，不弱化拒绝。无C执行/真实Provider或数据库迁移。

## 独立复审与后续

复审候选摘要见review-candidate.json；当前等待这次获准的正式独立复审，尚未写通过结论。通过后才能建立新开发冻结，旧r01/r02及失败检查点/三轮预审保持原件；不能更改旧冻结来制造通过。再恢复T069准备并冻结全链后选择全新e03，真实调用另需准确包批准。若本次仍失败则blocked交回，不自动续修。

## 最终验收

独立复审通过，见INDEPENDENT-REVIEW.md；评估助手实际运行113项相关测试，0skip，原手写fixture字节不变。随后将旧r02开发冻结原样归档为development-freeze-r02.json，再建立r03（a160fb21f78e48cd35004d94fe51cdbf1472feb1caf95ef501f737d0abe830bd），旧失败记录不追写。完整6组实际238 passed/0skip，XML /tmp/edumind-p15-t071-full.xml；严格mypy9源、Ruff/工作流/diff通过。原单项冻结漂移失败在新准确冻结下通过，断言未删改。

T071仅完成离线前置验收，本地完成提交成功后才恢复T069准备。独立e03、真实具体Schema兼容、准确新预算/外发/费用例外和实际模型质量仍未验证；T070未开始，不解除T038/catalog_only/H。
