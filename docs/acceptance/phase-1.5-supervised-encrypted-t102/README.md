# T102 受监督发送与加密证据：离线修复

本目录记录用户同意后的**一次限定离线修复**。样例是固定开发夹具，B 臂答案由夹具引擎生成；它不是模型基线、独立参考真值或教学通过结果。没有读取真实凭据、解析真实 DNS 或调用真实 Provider，也没有开放真实入口、选择正式样本或改变 T101 冻结。

## 实现与边界

- [控制器 v4](../../../scripts/isolated_diagnostics/p15_controlled_mock_v1.py)复用同一本预约账本、收据、候选绑定和固定分母；[加密控制器](../../../scripts/isolated_diagnostics/p15_encrypted_controller_v1.py)只接受[受监督合成传输](../../../scripts/isolated_diagnostics/p15_supervised_mock_v1.py)，不会装入真实网络 transport。旧 v2/v3 Mock 记录及先前失败复现保留；不要把旧线程原型当作修复后的真实发送能力。
- 每次合成请求由独立 watchdog 启动新 Python 发送子进程。子进程只经标准输入接收当前角色的合成 Key；启动参数和精简环境不携带 Key，也不继承其他角色的文件描述符。watchdog 先就绪，控制器在同一个锁内确认未停止后才发单字节许可。父进程退出会关闭唯一存活管道，watchdog 杀死并回收发送子进程。
- 停止时由控制管道请求 watchdog 终止子进程；只有收到 **子进程已回收的确认** 才把本机发送标为确认停止。watchdog 异常死亡、期限内无法确认或父进程崩溃后立即重开时，持久状态为 `stop_unconfirmed`，保留 unknown 占额，不补发。进程退出不能撤回已进入网络的数据，也不能证明远端不再处理或计费；本机同步文件系统或内核停顿不具备硬实时保证。
- 子进程中使用真实 `httpx.AsyncHTTPTransport` 的请求转换，底层 `httpcore` 连接池替换为内存拦截器，仅解析固定合成公网 IP。它检查原主机名 Host、SNI、证书校验配置、零重试和禁止重定向；**没有真实 TLS 握手**，因此不能推断证书、上游接口或服务商行为。
- [封存模块](../../../scripts/isolated_diagnostics/p15_synthetic_vault_v1.py)使用每批临时合成 AES-256-GCM 密钥。请求预约时的 SQLite rowid 作为单调 nonce，纳入 ledger seal；加密前先原子 claim 并封印，失败也不复用。AAD 绑定包、批次、槽位、臂、阶段、HTTP 状态、请求摘要、父收据、nonce 和子进程观察证明；账本只存密文引用及安全元数据。重开批次只读；密文／账本不一致、孤儿、篡改或缺失均停止，完整性不明的完成槽显示 `evidence_unknown`。
- [受限检查器](../../../scripts/isolated_diagnostics/p15_synthetic_guard_v1.py)在独立子进程扫描合成 Key 的字面与有界 JSON／Unicode 转义，超出可判定深度返回 unknown。检查请求及派生审核材料，响应先封存再检查；超限、未知及未运行保留原分母。它不能保证发现恶意服务使用任意编码或拆分方式泄露凭据；真实密钥隔离和跨供应商转发仍须在准确包中处理。
- 测试用 AES Key 与密文仅存放在相同的临时测试目录中（目录 `0700`、文件 `0600`）；不构成真实密钥保管设计。macOS 的 RSS 采样有超冲、地址空间限制并非此环境的硬保证，两个本地 ledger/anchor 同时回滚亦未被解决。

## 可检查证据

[压缩证据](offline-evidence.json.gz)包含 B/C 两臂共九次实际子进程 Mock 请求、原始合成响应、密文、加密引用及 AAD、子进程观察信息、候选、问题、审核和原账本快照。归档明文均为经检查的合成夹具内容，不含合成 Provider Key；临时 AES Key 不导出。归档检查器能重新计算密文摘要、请求/响应/父链、目标引文和账本 seal，**不能在没有密钥时重新解密该次归档密文**；生成当次和自动化测试在临时目录内实际完成 AES-GCM 解密与篡改反例。

[审查快照](audit-manifest.json)绑定本轮选定源码、测试、离线证据和既有冻结 manifest，供独立复核；它不是完整运行时闭包或真实执行包。运行 `PYTHONPATH=backend:. backend/.venv/bin/python scripts/isolated_diagnostics/p15_supervised_audit_manifest.py --check` 可核对这些文件的摘要。

```bash
PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-supervised-encrypted-t102/check_evidence.py
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_supervised_encrypted_t102.py -q
```

如需用新临时 Key 重新生成一次开发证据，可运行 `PYTHONPATH=backend:. backend/.venv/bin/python scripts/isolated_diagnostics/generate_p15_supervised_evidence.py`；由于进程 ID、临时路径和加密 Key 不同，新文件摘要会变化，不应覆盖已冻结的未来正式包。
