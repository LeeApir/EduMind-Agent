# T052：诊断上下文与失败留证修复

本地诊断防护缺口已修复并完成离线组合验证；**不代表中转追加指令／计数实现已修复，不能恢复真实诊断**。用户“修复”授权本次本地工作；T051具体提案中的供应商证据／运行契约仍未形成新的准确批准，不把该指令当作真实预算或硬界证明。

## 改动

新增 `scripts/acceptance_support/p15_guarded_transport.py`，未修改任何已冻结文件：

- `GuardedStrictDiagnosticAdapter` 组合原严格 Schema 适配器和新增观测层；原投影、完整本地 Schema、计数相等、模型／输出 usage 检查、先预约后发送与 unknown 停发保持。
- 在原传输器可以设置 proof／结算之前，拒绝额外或缺失 instructions、上限回显 null／不同、Schema 或 strict 改变、未完成响应和输入计数差异。允许的 system 合并仅为准确双换行拼接；不删掉中转指令后冒充验证通过，不修正计数或退款。
- 两端分别在发送前记录公开 origin/path、方法、准确 body SHA／长度；接收后先记录 HTTP 状态，再读取／限长／凭据回显检查，把安全原件和 SHA 持久化后才解析、验证。失败另记固定白名单原因及各完整性缺陷，不序列化异常消息或请求／响应头。证据文件排他创建、权限0600、flush/fsync；审计目录要求私有权限。留证写入失败即停止，不准入。
- 单次实例绑定计数与生成的准确 body，拒绝重复计数或重复生成。兼容原 SSRF guard 的固定公共 IP＋准确 Host/SNI 发送；不会因 IP 固定把正常组合误拒绝。
- **新版本只接受显式 `httpx.MockTransport`**，其他传输在新审计目录创建及网络发送前拒绝。没有新增 CLI 或接线生产工厂／r03 入口。回执相同只说明未发现矛盾，不能提供事前供应商硬界证明，因此当前不提供真实启动绕行开关。

## 验证

最终命令：

```sh
PYTHONPATH=scripts:scripts/tests backend/.venv/bin/python -m pytest -p p15_guarded_isolation_plugin scripts/tests/test_p15_guarded_transport.py scripts/tests/test_p15_input_count_audit.py scripts/tests/test_p15_strict_schema.py -q --junitxml=/tmp/edumind-p15-t052-offline-r06.xml
backend/.venv/bin/ruff check scripts/acceptance_support/p15_guarded_transport.py scripts/tests/test_p15_guarded_transport.py scripts/tests/p15_guarded_isolation_plugin.py
```

50 passed、0 skipped：新增17项防护／失败／泄漏／留证／适配器组合，T051准确证据与反例9项，原严格 Schema 24项。新增测试禁止 DNS、socket connect 和 .env 文件读取。覆盖实际 r03 原件（仍拒绝）、把计数改为相等但保留额外指令和 null 上限（仍拒绝）、干净对照（允许原账本结算）、完整本地 Schema 对抗样本（仍校验失败、费用按原规则保留）、HTTP 503、坏 JSON、超长、超时异常携带凭据、请求／回执凭据回显、磁盘失败、请求体绑定及真实传输拒绝。

失败记录保留：r01 13通过/1失败，发现组合测试的固定 IP 需要匹配 Host/SNI，已修复；r02新增15通过；r03新增17＋T051九项共26通过。扩展 r04 中48通过/2失败，旧预执行测试错误假设历史 r03 输出目录不存在；r05隔离路径名还不满足原 `-r03` 命名断言，两失败仍保留。新增显式 pytest plugin 仅把这两项测试的 OUTPUT 指向各自临时父目录，保留原文件名及全部原断言；不删除真实证据，不改冻结测试、不跳过任何用例。r06最终50全部通过，原失败XML均保留 `/tmp/edumind-p15-t052-offline-r01.xml` 至 `r06.xml`。

原 r02/r03 结果 checker 仍预期退出2，准确核对两个 stopped 批次及所有原始 SHA；T051只读 audit、工作流、Ruff3与 diff 通过。准确命令、XML与源码 SHA见 validation.json／manifest.json。

## 边界与交接

新增真实请求0。T052完成本地修复，T038继续blocked；累计仍4 HTTP／2生成，unknown合计64k输入／16k输出，未改旧账本或恢复剩余授权。未重启r03、未创建或执行r04、未继续完整课程或T039，不push／merge／部署。

下一步若需让该候选可真实使用，必须先取得中转最终上下文、同口径计数与上游输出强制上限的可核对证据；本地无法修复供应商服务。任何运行契约或可用性例外仍须具体设计／准确批准，真实探测另报最小准确预算。本次不申请、不执行真实探测。
