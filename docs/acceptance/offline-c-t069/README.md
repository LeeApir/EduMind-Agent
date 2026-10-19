# T069：完整离线流程与统一证据

```text
backend/.venv/bin/python -m pytest -q scripts/tests/test_offline_c_evidence.py
backend/.venv/bin/python scripts/run_offline_c_checks.py --manifest docs/acceptance/offline-c-fixtures/manifest.json --suite all --output /tmp/edumind-offline-c-report
backend/.venv/bin/python scripts/check_offline_c_report.py --report /tmp/edumind-offline-c-report-final/report.json
```

实际完整流程先在要求的 `/tmp/edumind-offline-c-report` 执行：27编译/17程序进程、预登记观察全符合，但校验器缺Path导入，Ruff和实际检查均失败。原报告/每例/执行器源码保留于attempt01；修复后13项篡改回归通过，再在独立 `...-final` 目录重跑并校验。最终55项零调用回归通过，27编译/17程序进程和统一证据校验通过；本任务两次实际all累计54编译/34程序进程，无Provider。

[最终报告](final/report.json)含12项检查pass、9项fail、6项not_run。这是“完整执行且检出预期缺陷”，不是所有程序通过：EduMind严格缺换行、OM不可编译/NULL访问及3反例都保留失败，OM main运行未补造。普通/严格、main/接口、数值/格式、ASan/UBSan/显式追踪与LSan未运行均分列。

报告保存逐例文件、原始有界命令输出、全部输入/驱动/规格/工具链/源码绑定、实际隔离探针、清理和计数。report.seal.json与report_binding检测字节变化，校验器还重算来源、case集合、准确flags/argv、进程退出/信号、观察/结论与预登记条件，外层重算摘要仍不能混样本、缺证据、改状态或伪称LSan。具体拒绝有13项回归。摘要不是密码学签名或远程执行证明；可信来源是本地维护者记录和版本历史。

`runtime-source/` 保存每一轮报告实际绑定的8个执行文件，逐文件SHA已核对，包含失败导入版本。原执行源码在后续改变时，须用报告冻结源码复核，不能用当前新版本刷新旧证据。最终报告和cases可独立读取，失败目录不改成新pass。

工具不读取Provider key、不调用模型、不连接数据库或发布接口。`publication_qualified=false` 始终明确；不能把离线证明写成模型pass、人工签核、通用安全结论或T040准入通过。环境不可用、超时、输出超限及无完整子进程证据均不合格，不能使用宿主编译器回退。
