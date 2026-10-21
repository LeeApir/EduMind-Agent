# Qwen HTTP400 独立单次定位

用户明确要求“测试qwen为什么拒绝”，授权本次单次定位。旧qwen-review-execution-r01及所有旧停止记录不恢复，非候选质量复活。

仅重复旧首例准确wire（模型qwen3.8-max-0902、非思考、strict json_schema、8192/60秒），只改变错误诊断采集。1次、无重试/回退/修正，输入输出保守预留13.420260元，全价计不假定免费；输出预算8202，独立SQLite先预留后取Key，失败用量未知不记零、不退款。隔离测试PG与真实临时连接/目标/撤销边界沿用旧执行器。

HTTP错误正文仅内存读取，64KiB上限；持久化仅白名单错误码及技术词/当前Schema字段名，未知词替换，原始正文/headers/密钥不留。任何结果后持久停止；即使偶然获得完整审核也不承认候选质量通过，不运行下一条。新诊断不是T040正式验收或新模型筛选。

离线：backend/.venv/bin/python -m pytest scripts/tests/test_qwen_http400_diagnosis.py -q（3 passed）。真实入口：backend/.venv/bin/python scripts/diagnose_qwen_http400.py，专用PG环境由run_catalog_db_tests.test_environment提供，勿打印凭据。
