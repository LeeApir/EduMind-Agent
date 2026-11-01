# T102：三个阻塞的限定离线修复与 B/C 证据

本目录是 `fd9105f` 之后的**新离线版本**，不覆盖[上次失败记录](../phase-1.5-supervised-encrypted-t102/FINAL-REVIEW-BLOCKED.md)、其 29 文件审查快照或 T101 的 238 文件冻结。这里只处理用户列出的三个阻塞并运行一组固定开发夹具；结果待独立复审，不是模型质量、课程可评或真实接口通过结论。

## 三个修复

1. [进程启动](../../../scripts/isolated_diagnostics/p15_spawn_isolation_v2.py)在本机 Darwin / CPython 3.11 使用系统 `posix_spawn`，设置 `POSIX_SPAWN_CLOEXEC_DEFAULT`，只显式继承必要管道；不支持的平台和不符合策略的参数直接失败，没有 fork 回退。发送子进程只从管道接收当前角色的合成 Key；合成密钥检查器逐角色单独运行。B/C 测试也禁用了父进程的 Python fork 路径并检查环境和继承描述符。此结论限当前离线调用路径，不能当作生产密钥保管结论。
2. [监督器](../../../scripts/isolated_diagnostics/p15_supervised_mock_v2.py)绑定批次截止时同时固定对应的单调时钟截止；监督进程独立检查批次绝对时间和较早的单次截止。发送前再次检查，父事件循环被阻塞不提供新派发许可。系统调度或内核停顿仍不是硬实时保证；该入口的 DNS、连接池和 Key 均为合成实现。
3. [封存控制器](../../../scripts/isolated_diagnostics/p15_encrypted_controller_v2.py)检查每个已响应行的引用、状态和摘要，并校验密文、AAD 与原始响应；已完成槽还必须具备正确的阶段序列、响应状态和与原始响应匹配的用量。缺失或矛盾的完成证据使批次停止、该槽记为 `evidence_unknown`，不改变固定分母。未完成／失败响应若用量未知，继续保留原始密文与失败状态。

[反例测试](../../../scripts/tests/test_p15_isolated_blockers_t102.py)保留原来的 11 秒父循环阻塞和删除密文／元数据并重算本地 seal 两种条件，增加缺失用量、摘要不符、缺行等情况。[双臂及恢复测试](../../../scripts/tests/test_p15_supervised_encrypted_v2_t102.py)覆盖 B 四次、C 五次模拟 HTTP，首审含实际结构的目标 ID 与证据引用，然后修复并重审；还覆盖加密原件、停止、迟到、超限及崩溃恢复。

## 可检查材料

- [B/C 合成请求和收据](offline-evidence.json.gz)：9 次 Mock 请求、合成原响应、两臂候选／意见与修复父链、临时密文及账本快照。AES Key 未导出；生成当次已在临时目录解密验证，归档检查只能重新核对密文摘要，不能重新解密原密文。
- [证据重放](check_evidence.py)：检查两臂请求／响应 Schema、实际可见引用、B 臂反馈核对记录、两臂父链、AAD 及账本摘要。依既有规则，C 臂没有单独的反馈核对记录。
- [原失败复现](../phase-1.5-supervised-encrypted-t102/reproduce_review_failure.py)：旧版本仍按原义保留，成功复现缺口时退出 2；它不应被误认为新版本的通过测试。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_isolated_blockers_t102.py scripts/tests/test_p15_supervised_encrypted_v2_t102.py -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-isolated-blockers-t102/check_evidence.py
```

测试中的答案、审核和用量均是合成夹具；未读取真实 Key、未访问真实 DNS 或 Provider、未选正式独立样本。离线 AES Key 与密文位于同一临时目录，不能用于真实凭据保管。受控 Mock 不是可发送真实请求的适配器；真实接口、TLS、服务端限额和费用尚未验证。旧批次余额、签核和正式验收标准不变。
