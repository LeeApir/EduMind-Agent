# Animation DSL v1 本地校验资产（T023）

契约来源：[已批准 ADR-0010](../../../docs/ADR/0010-constrained-animation-dsl.md)及[实际批准记录](../../../docs/ADR/0010-dsl-approval-20261004.json)。`schema.json`按批准附件原字节复制，SHA256为`f9a76377aa74745e39593d518b185dd886be80760f76eefaca42ed4494c63258`；保留原提案title，不修改历史提案或批准清单。`policy.json`将批准的字节/深度、累计节点/边及总时长限额落实为版本化运行数据。规则变化须新契约批准及新摘要，不能用相同版本掩盖限额变化。

入口为`app.services.animation_dsl_validation.validate_animation_dsl(raw, knowledge_point_id=...)`，仅接收bytes/str JSON和服务端授权目标，完整候选先通过严格JSON/schema/text，再按动作顺序模拟。固定失败`DSL_SCHEMA_INVALID`、`DSL_REFERENCE_INVALID`、`DSL_RESOURCE_LIMIT`只携带可选动作索引，不包含候选片段。schema层普通错误优先于同层maxItems；字节/深度在解析前检查。

成功返回不可变`ValidatedDSL`：规范JSON、逐步冻结的节点/边/指针/访问/样式/比较/复杂度轨迹、累计整数时间，以及DSL、轨迹、schema、policy、校验器实际字节SHA256。`candidate`每次返回新副本，不能修改已验证轨迹。对象和指针按创建/声明顺序排列；compare仅当前动作有效，swap仅交换值，disconnect保留历史ID配额。自由文本是显示字面量，没有文件访问/执行或模型调用。

本地有效只是审核候选，不授予发布权限。教学事实、复杂度与字幕注入意图由T025独立审核；T024负责可信编译/AST，T027负责隔离渲染，T028才接产品请求。T023不增加HTTP、Job、Provider请求或动态开放，默认目录基线保留。批准示例不是正式教学/真实Provider验收数据。

验证：`cd backend && .venv/bin/python -m pytest -q tests/test_animation_dsl_validation.py`；Ruff/mypy检查本模块。测试包括批准的22例（其中两例必须通过本地结构检查并留待独立审核）及独立JSON、Unicode、严格整数、时间/对象/累计资源、历史ID、状态/比较、代码字面量不执行与不可变摘要回归。
