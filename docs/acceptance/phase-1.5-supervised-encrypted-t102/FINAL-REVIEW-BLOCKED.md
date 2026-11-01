# T102 限定离线修复：最终独立复审未通过

本次按用户同意的范围完成一次隔离修复并交两名独立子助手复审。审查快照为 [audit-manifest.json](audit-manifest.json)，SHA256 `3e906fb9de46a20186f80122f5f00f47dec01d235886cc2d5741e1ba54bab134`；29 个列入快照的文件审前、审后均匹配。快照不是完整运行时闭包或真实执行授权。

结论：**本次修复未通过，T102 blocked，不自动追加修复。** 测试均只使用合成密钥、合成课程、合成 DNS 和被内存池拦截的 HTTPX；真实密钥读取与真实 Provider 调用均为 0。

## 独立复审发现

1. **凭据进程隔离不符合已批准约定。** 当前发送 supervisor 使用 `subprocess.Popen`，参数包含 `close_fds=True`、非空 `pass_fds`、`cwd` 和 `start_new_session=True`。本机 CPython 3.11 的 `subprocess.py` 在这些条件下走 `_fork_exec` 而非 `posix_spawn`；对该解释器执行 `otool -tvV` 可见 `_do_fork_exec` 调用 `_fork`。父进程此时持有两角色合成 Key，故 exec 前会短暂继承其地址空间；精简环境和关闭文件描述符不等于从未 fork 继承。实际仅涉及合成 Key，没有发现读取或发送真实 Key。
2. **watchdog 未独立执行更早的批次截止。** watchdog 只接收 `monotonic()+wall_seconds`，未接收包中可能更早的绝对截止。独立评估用批次剩余约 5 秒、watchdog 30 秒，待子进程到达模拟派发前暂停点后令父事件循环同步阻塞 11 秒；首次 Mock 派发发生在批次截止后约 5.7 秒。父循环恢复后才返回超时并停止。该反例说明 watchdog 未独立约束批次窗口，不只是同步文件系统调用不能保证硬实时。
3. **汇总可忽略已登记响应缺失。** 对完成的合成 B 链，将一条 `responded` 记录的响应引用、摘要、HTTP 状态和用量置空，同时删除该条密文，再显式重算本地 SHA seal；`fixed_denominator_summary()` 仍显示 `complete / mechanical_complete / evidence_integrity=verified`。复现中的重算是为了检查状态机自身是否识别内部矛盾，不表示这里证明了可信目录之外的攻击。原因是 inventory 只枚举 `response IS NOT NULL`，没有检查 `responded` 必须具有完整引用与用量。

[复现脚本](reproduce_review_failure.py)在临时目录运行第二、三项合成反例，成功复现时故意退出 **2**；其中模拟父事件循环阻塞约 11 秒。第一项可用本机 CPython 源码及以下只读命令检查：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-supervised-encrypted-t102/reproduce_review_failure.py
otool -tvV backend/.venv/bin/python | rg -m 1 -A 32 '^_do_fork_exec:'
```

## 已保留的进展与限制

- 相关离线回归 **468 passed**；其中受监督／加密链 **38 passed**。这不抵消上述独立反例。
- 九次合成子进程请求、父链、可见引文、密文摘要及账本检查见 [证据说明](README.md)；旧 238 文件冻结和历史证据重放通过。归档未导出临时 AES Key，因此归档检查不能重新解密该次密文。
- 此快照仍强制禁用真实 Provider 入口，不开放生产，不选择正式样本，不冻结真实执行包，不继承旧批余额。密文／密钥在同一临时测试目录、RSS 采样超冲、双份本地状态同时回滚、任意编码回显及真实 TLS／上游行为等限制仍未解除。

按本次明确范围，“如果本次限定修复仍失败，重新报告而不自动追加修复”。后续需要重新评估进程创建、独立截止和证据完整性设计，再由用户决定是否开展新一轮工作；本记录本身不授权任何真实调用。
