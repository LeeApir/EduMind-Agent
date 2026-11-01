# 单组 B/C：限定离线实现未通过独立复审

**结论：T102 仍 blocked。** 用户已采用 [A、B、D 及 C2](../phase-1.5-manual-bc-contract-diff-t102/ADOPTION.md)；本次不研究内核级绝对截止，不把金额硬封顶当作前置。以下全部是合成数据；未读取真实密钥或调用真实 Provider。新原型不是可执行包、正式审核链或教学评估，不能用于真实材料。

## 独立复审阻塞

1. **停止后仍可投递任务。** 首版在子进程创建期间调用 `stop()`，返回 `stop_unconfirmed` 后仍可投递并返回结果；增加停止事件与启动后检查后，独立评估者又在检查后、`communicate()` 前暂停，复现停止未确认返回后合成任务仍被送到子进程并执行。父进程只在子进程完成后丢弃结果。独立评估者和开发执行者均运行 [复现脚本](reproduce_stop_race.py)，结果为 `stop_unconfirmed`、`job_sent_after_stop=True`、`child_acted=True`、`STOPPED_RESULT_IGNORED`。这是 Mock 子进程，不是实际网络发送。两轮不同停止检查仍未满足“一旦停止不得继续”，按项目协议不追加修复。
2. **异常原件丢失。** [收据原型](../../../scripts/isolated_diagnostics/p15_manual_receipts_v1.py)在加密封存前解析用量；非法 JSON 抛错后没有保存可安全保存的原始合成响应。独立评估者与开发执行者均运行 [复现脚本](reproduce_receipt_failures.py)：`JSONDecodeError`、无响应密文、仅有预登记。
3. **迟到后的状态未接线。** 同一复现还表明收据原型记录 `late` 后仍允许登记下一阶段；它尚未绑定不可逆停止账本。局部校验不能当作完整 B/C 状态机。
4. **其他未闭合边界。** 独立评估者在可替换目录的前提下复现：原件目录被替换为符号链接时，检查报错前合成请求已写到链接目标。还发现 B 臂可登记 `C_plan` 并获得局部 `verified`、收据目录无法只读重开完成崩溃恢复；独立 witness 与账本同时回滚时无法检测前缀缺失。当前进程环境只检查另一角色凭据的**名称**，不能证明祖先进程内存或描述符不含另一角色凭据。以上结论只针对合成原型和明确前提，不声称真实凭据已泄露。

## 本次工作及验证

- 用户确认的条款以单独[采用记录](../phase-1.5-manual-bc-contract-diff-t102/ADOPTION.md)绑定旧提案摘要；旧提案、旧 238 文件冻结、旧 50 文件审查快照及旧失败均未改。
- 新增 [合成单次监督原型](../../../scripts/isolated_diagnostics/p15_manual_supervisor_v1.py)、[绝对路径隔离子进程](../../../scripts/isolated_diagnostics/p15_manual_child_v1.py)、[局部证据检查](../../../scripts/isolated_diagnostics/p15_manual_evidence_v1.py)与[合成收据原型](../../../scripts/isolated_diagnostics/p15_manual_receipts_v1.py)。它们尚未完成可信依赖闭包、独立可信凭据祖先、完整控制器与真实安全传输接线；不能用于真实 Key 或出站。
- 相关基础测试 **10 passed**，Ruff 通过；这些测试未覆盖上述独立反例。严格 mypy 对收据原型有 **1 项类型错误**（第 60 行），未将其记为通过。用户要求的完整 B/C Mock 生成—审核—修复—重审链、新准确包、独立选样和执行器/策略冻结均**未完成**。
- 独立子助手 `/root/offline_contract_review` 完成只读复审，身份为 `assistant`；共享工作区不构成物理隔离。审查版本 SHA-256：supervisor `6a742a0e6d080726c7227fc63d41ca79703bd83967f8d56716f44ef132903f58`，receipts `e6e1442c5f5350f8f51007d8fe7944729207efdc42f4cd62bb75753fecb2e80a`，evidence `b61fb3114fcfbb35fedb518f360a83bd416f8e9737f3a9dbaa7d8a3d66f8ea93`。

```sh
env -i PATH=/usr/bin:/bin PYTHONPATH=backend:. PYTHONDONTWRITEBYTECODE=1 \
  backend/.venv/bin/python docs/acceptance/phase-1.5-manual-bc-offline-t102/reproduce_stop_race.py
env -i PATH=/usr/bin:/bin PYTHONPATH=backend:. PYTHONDONTWRITEBYTECODE=1 \
  backend/.venv/bin/python docs/acceptance/phase-1.5-manual-bc-offline-t102/reproduce_receipt_failures.py
```

## 需要决定

下一步如继续，需要限定地重新设计**停止状态与任务投递的因果关系**，以及**先封存原件、再解析并绑定独立登记/不可逆停止/恢复**的方案；先以这两份反例和目录替换、错臂阶段、恢复反例验证，再交独立评估。另一选择是暂停本实验并重新评估单组探索路线。此前 C2 仅为本批预算方向，不是准确批次或真实调用授权。

依据 [AGENTS.md](../../../AGENTS.md)：“同一问题两轮有实质区别的修复仍失败……及时标记 `blocked` 并向用户求助。”本次停止竞态已连续出现于两轮不同检查，故停止追加修复，不冻结、不选样、不真实调用；等待用户决定。
