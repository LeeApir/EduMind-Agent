# T102 本轮限定离线修复：独立复审未通过

结论：**blocked**。本轮只使用合成 Key、合成材料、临时账本和内存拦截的 Mock HTTP；未读取真实 Key 或调用真实 Provider。按用户约定，复审失败后不追加修复，也不进入有条件批准的真实探索测试。

## 进程启动的代码身份缺口

独立评估者发现一个需要明确前提的反例：如果继承的工作目录可由攻击者放置同名 `scripts` 包，子进程的 `python -m` 会先加载该目录中的模块。临时合成复现里，替代的合成 Key 检查器和 watchdog 先于项目模块执行；假 watchdog 收到**当前角色的合成 Key**，控制器随后才发现响应异常并停止。该反例没有取得另一角色的 Key、真实 Key，也没有访问网络；当前真实调用入口仍未开放。

[完整复现](reproduce_cwd_shadow.py)只在临时目录创建同名合成模块：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-isolated-blockers-t102/reproduce_cwd_shadow.py
```

独立评估者与开发执行者均观察到 `shadow_watchdog_ran True received_current_role_synthetic_key True`。这不推翻本机 `posix_spawn` 避免原 fork 地址空间继承的观察，但说明目前未将实际加载的子进程代码身份绑定到可信目录；不能据此认定进程隔离已通过。

## 未闭合的响应证据缺口

独立评估者复现：合成 B 请求已收到完整响应，停止后该响应保存为 `late`，密文存在，记录用量为 10／20。随后在临时账本中删除该密文、把该行响应引用、摘要、HTTP 状态和用量同时置空，并显式重算本地 SHA seal。汇总仍显示：

```text
batch=stopped
slot=failed_or_unknown
denominator=1
evidence_integrity=verified
```

批次和槽位均保持停止／失败，**没有被误报为成功**；错误是该 `late` 状态已经表明曾保存迟到响应，但原件与元数据消失后，完整性仍被标为 verified。[完整复现](reproduce_late_missing.py)使用临时目录，并通过重算 seal 单独检验状态不变量，不代表证明了可信本地目录外的攻击。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-isolated-blockers-t102/reproduce_late_missing.py
```

独立评估者与开发执行者均实际运行，输出包含 `late_result: MOCK_LATE_RESPONSE` 和上述汇总。当前实现检查 `responded` 必须有响应，但没有对 `late` 加同等约束，见 [封存控制器](../../../scripts/isolated_diagnostics/p15_encrypted_controller_v2.py)。原 `responded` 缺失反例已通过，新发现的问题仍属于用户指定的响应证据完整性范围，因此整轮不通过。

## 已保存的结果

- 原反例、B/C 修订链及相关回归共 **687 passed**；独立评估者重新运行本轮两组测试为 **47 passed**。这些测试未覆盖上述迟到反例，不能替代独立复审。
- 独立评估者还分别以较早的批次截止和较短的单请求截止，在父事件循环阻塞 11 秒时验证未发生迟到 Mock 派发；这只说明所测截止场景通过，不消除上述代码身份缺口。
- 两臂实际产生的九次合成请求、原响应、首审问题、修复父链和重审收据见 [证据与入口](README.md)。归档不含临时 AES Key，只能重放密文摘要，不能重新解密该次归档。
- 50 文件独立审查快照 [audit-manifest.json](audit-manifest.json) SHA256 为 `8c29961e0fd2754400aeb5021fbc9c812147612d829a580a563cda9d18473a66`；独立评估者审前审后均核对一致。旧 238 文件冻结及旧 29 文件审查快照也已核对保持。
- 开发夹具不能替代独立选样、真实模型课程、教学评价或真实传输验证；真实密钥保管、准确包及预算尚未完成。

T102 保持 blocked；如需后续工作，应由用户决定处理方向，不延续旧批次、旧余额或隐含授权。
