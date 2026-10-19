# T068 所有权及分配失败实际结果

```text
backend/.venv/bin/python -m pytest -q scripts/tests/test_offline_head_insertion_checks.py
backend/.venv/bin/python scripts/run_offline_c_checks.py --manifest docs/acceptance/offline-c-fixtures/manifest.json --suite ownership --output /tmp/edumind-offline-c-ownership
```

42项准入/监督器/所有权Mock回归通过，与Docker实际C运行分开。实际19编译/15程序进程、19案例均符合预登记观察；坏程序/反例仍是fail，OM四个main运行仍是not_run。完整结果见ownership.json，摘要见summary.json；实际有效隔离及v3工具链锁见offline-c-toolchain-t068。

EduMind原main与独立函数接口分别正常及malloc1/2/3失败共8场景通过，每次失败保持旧链，stdout依次为3/2/1、3/2、3/1、2/1；所有实际分配恰好释放一次。原main的局部head置空没有被直接观测，记录null；独立函数驱动中由caller明确置空，与free_list的按值接口分开。

OM原main编译失败不能运行，不补typedef修好它。独立函数驱动正常通过、freeList(&head)清空及再次空释放通过；第1/2/3次分配失败均在原函数检出NULL访问，已发的部分事件/UBSan诊断保留，缺失的最终分配/释放/live/输出全部不推导填值。

丢链、重复释放、忽略main返回值三份派生反例均实际异常退出且被指定断言检出。ASan/UBSan确有编译/运行证据，显式slot追踪单列；未运行LSan，不声称普遍内存安全或正式审核通过。

首次准备因重复写只读派生文件失败发生在C编译前，保留preparation-attempt-01.json；改为合并清单后只复制一次并加回归，没有改变文件权限或降低隔离以通关。
