# 固定 C 样本准入包 v1（T066 工作成果）

依据 [ADR-0019 具体批准](../../ADR/0019-approval-20261019.json)。此包只登记两份封存头插法原件和历史固定驱动，不是任意代码执行入口。

- EduMind：从 `complete-review-case.json` 唯一 code 候选提取 UTF-8 原 source，保持缺末尾换行；原 main、包装 main 和接口检查保持区别。
- OM：从原 ZIP 的唯一 manifest 及4个指定文本元素按已记录排版规则提取，与封存原程序/函数片段逐字节一致；不补 typedef 或修正原 main。函数驱动的测试别名及 Node** 调用独立登记。
- 独立预期来自批准的固定矩阵；模型 expected_output 不是测试真值。原课程仍没有因此获得人工签核或正式发布资格。

`manifest.json` 绑定10份执行输入/规格，`review-registry.json` 记录本地维护者对这些准确字节的技术准入审阅。它不是模型审核结果或用户教学签核。检查器固定 manifest 摘要，来源/驱动/规格/审阅变化均需新的明确登记和代码评审，不能修改两份JSON后自行通过。

```text
backend/.venv/bin/python -m pytest -q scripts/tests/test_offline_c_fixture_manifest.py
backend/.venv/bin/python scripts/check_offline_c_fixtures.py --check
```

16项零执行测试通过。检查器不调用编译器/Docker/模型/数据库；拒绝未列入名单、摘要变化、未审阅、额外文件、越界路径、软/硬链接和伪造设计批准。原件来源始终只读。

**工具链仍阻塞，T066尚未完成。** 批准的2025-10-15快照与基础镜像的libc版本冲突，APT准备退出100；没有安装编译器、构建最终镜像、运行探针或执行C。准入检查成功只证明固定输入登记有效，不能授予执行资格。实际环境失败及最小调整提案另存独立证据，不修改已批准ADR0019或原manifest。
