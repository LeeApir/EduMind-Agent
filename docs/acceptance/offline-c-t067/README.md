# T067：固定原程序编译与输出

零Provider，普通/严格编译与原程序/接口驱动分开。工具链及可信探针新锁见 [lock](../offline-c-toolchain-t067/lock.json)；保留T066锁，不原地更改旧镜像。

```text
backend/.venv/bin/python -m pytest -q scripts/tests/test_offline_c_runner.py
backend/.venv/bin/python scripts/run_offline_c_checks.py --manifest docs/acceptance/offline-c-fixtures/manifest.json --suite compile-output --output /tmp/edumind-offline-c-compile-output
```

已实际执行上述命令；监督器失败/未运行证据补齐后，使用新 `/tmp/edumind-offline-c-compile-output-final` 目录复核，未覆盖首次报告。final报告8次编译、2次实际原程序运行，全部符合预登记观察；两次suite合计16编译、4次原程序运行。20项监督器Mock回归+16项准入回归通过，与实际C证据分开。

- EduMind：严格失败（原字节缺末尾换行）；普通编译通过且保留警告。正常main及ASan/UBSan版本main退出0，原始stdout为 `3 2 1 \n`，数值/独立字节规格一致，模型claim的末尾格式不一致另列。
- OM：严格/普通原件编译均失败，保留真实诊断；两个main运行项均not_run/compile_failed，不用函数驱动代替。失败被检出不等于原程序通过。
- LSan未运行；尚未执行分配失败/所有权矩阵，不由正常路径推断全部内存安全。

真实预检核对inspect有效参数、容器UID/GID/cap/seccomp/禁止提权、root及包只读、无出站路由、cgroup与文件/磁盘限额，并实际触发宿主超时/输出限制与子进程64KiB限制，所有确切容器已删除。第一次超时探针的宿主组信号PermissionError保留；纠正为Docker终止容器后等待/终止本次自有CLI，不放宽隔离。

报告保存完整命令、绑定、限制与退出/原始有界输出。CLI只允许固定manifest与case，输出目录必须新建；环境不可用明确未运行并失败退出，已启动但证据无效记protocol_error且不推测子进程结果。没有Provider/数据库/宿主C回退，不能据此修改审核、人工决定或发布资格。
