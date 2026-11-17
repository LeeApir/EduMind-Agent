# T067 受限示例引擎交接

实现 scripts/isolated_diagnostics/p15_head_insertion_engine.py：准确规格校验、逐语句抽象状态、局部/调用者头区分、四种变体与分配掩码、有限观察/答案、固定C展示模板与同源动作。示例每次绑定规格/引擎/模板/内容摘要，答案和动作派生前重算拒绝篡改。

范围仅ADR0041固定模板，不运行C、不读文件/Key、不依赖Provider或数据库，不接线生产API/评分/掌握度。reachable_prefix是到第一次重复/不确定指针前的可知前缀，不能解释成循环或未初始化程序的完整输出。C源仅展示，不提供内存安全或泄漏清理保证；初始链预先正确构造，分配掩码是合成前提。

开发证据 development-example.json 包含正常三次插入的全部状态和动作。六份手算开发种子逐字段验证，额外覆盖非空/重复/负值/边界、全部失败、失败掩码组合、数值重命名、逐语句黄金状态和错误输入；不以被测引擎生成测试期望。手算由开发助手完成，不冒充人工独立真值签核，T069独立评估材料尚未建立。

实际验证：

```
backend/.venv/bin/python -m pytest scripts/tests/test_p15_head_insertion_engine.py -q --junitxml=/tmp/edumind-p15-t067.xml
backend/.venv/bin/mypy --strict scripts/isolated_diagnostics/p15_head_insertion_engine.py
backend/.venv/bin/ruff check scripts/isolated_diagnostics/p15_head_insertion_engine.py scripts/tests/test_p15_head_insertion_engine.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

50 passed、0skip；严格类型1源通过、Ruff/工作流/diff通过。未运行任何C编译/解释/执行或PG、Provider，HTTP0；这些均不是缺环境skip，而是本任务明确范围外。代码自查了分配失败优先、原始/新节点可达性、返回值丢弃、自环与indeterminate停止、行号绑定及派生篡改。下一T068实现独立内容/动作协作与故障Mock，生产及T038状态保持。
