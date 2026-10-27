# T062 生成请求语义约定交接

按用户明确指令完成两项内部改进中的第一项；边界见[ADR0039](../../ADR/0039-generation-semantics-and-consistency.md)。场景请求升级free-scene-generation-v4，服务端semantic_contract=v1包含C参数按值、返回新头接回、malloc初始化、复杂度前提、题干/代码/答案同一调用状态等约定。原输出Schema/题数/形式/画像及安全/评分权限不变。

对实际必要上游的专用C代码块，pycparser3.0只在内存解析，记录准确scene/version/content digest/代码SHA及接口来源。识别明确声明层级及直线分配→next接旧头→局部改头→返回新头的受限语法模式，函数改名同样识别；不是编译器、控制流/别名/内存安全或答案正确性证明。宏、扩展、语法/大小/节点/递归边界失败为not_assessed，不能猜测完整语义。只去除允许标准include声明，不打开任何header，不运行cpp/生成C/子进程或网络。

pycparser3.0原已存在锁中，本次提升为明确直接依赖，原wheel/sdist SHA及所有版本不改。首次uv离线resolve因旧celery缓存不足失败；仅补锁中root依赖边及requires-dist，实际uv lock --check --offline随后通过。不是把失败resolver当成功。无下载/模型调用。

实际97 passed / 0skip：

- backend目录pytest `tests/test_free_scene_semantics.py tests/test_free_scene_answer_contract.py tests/test_free_scene_form_contract.py`：40，含新17/旧13+10，完整新增payload字节门禁、输入原样/Schema和引用绑定、无文件/网络/子进程及未知边界。
- `python3 /tmp/edumind-t062-pg.py`（可复现归档run_pg_offline.py）：真实隔离PG新v3/v4共存1＋既有v2/current共存1＋形式PG1＋原生成54＝57。实际历史97130f5生成者及原Schema加载，不伪造旧version标签；原候选/摘要/幂等/owner隔离保持，无自动ready/签核。
- 新两源mypy、相关Ruff、uv锁检查、工作流与diff通过；代码自查，不宣称独立评审。新PG无连接泄漏，既有生成测试保留3条已知GC警告及Starlette弃用警告。

证据XML/SHA见validation.json。真实Provider0。与用户授权的T063连续执行期间专用PG保持运行，本轮末尾统一恢复exited。旧r05/单次sol/所有旧签核与H不改，旧包在新源码下不再匹配其冻结SHA，不能因此修改旧包或冒充真实质量已改善。

下一项T063把受限一致性观察接入既有私有审计，只作待复核建议；本项不改变硬准入、不自动修复或调真实模型，T038仍blocked。
