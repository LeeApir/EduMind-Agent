# 独立版本化知识结构

ADR-0012 A–D与准确设计附件已获批准，见[批准登记](../../docs/ADR/0012-graph-approval-20261009.json)。`expansion-v1/`是批准时的只读提案材料，Proposed字样保留历史语境。

T031发布`phase-1.1.0.json`（schema2，30节点/69边）、`phase-1.1.0.sources.json`及文件摘要manifest。原`../knowledge_graph.yaml`（schema1/mvp-0.2.0/10节点）字节保留；默认应用仍读取原图，已签核目录包未改。T032负责显式版本配置/查询与catalog依赖隔离；本次发布文件不切换默认图或开放动态能力。

schema2保留原节点字段，新增root `references.file/sha256`；来源sidecar必须为同目录普通文件，禁止路径穿越/绝对路径/URL/符号链接。SHA256使用sidecar解析对象的UTF-8规范JSON：`ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False`，按对象内容而非排版绑定；manifest另记录真实文件字节SHA256。sidecar schema1固定graph_version/checked_at/sources/node_references/qualification，完整覆盖节点，来源链接只作为HTTPS元数据，不由loader获取或执行。

schema1保持原`manual_fact_checked`历史状态；schema2使用`reference_checked`，表示编写者对参考/结构的核验，不能冒用人工课程签核。原10节点全部教学元数据保留；新增节点的mastery_rule_key为`graph-metadata-v1`标签，不新增掌握度算法或学习证据。source sidecar的metadata_only不决定原目录课程是否可学，也不授予新20节点正式资源资格。正式资源、可评分题、媒体、用户掌握度及路径提交仍使用已有独立门禁。

`KnowledgeGraphRepository.from_file(path)`按版本验证并读取来源；`from_payload(payload, reference_payload=...)`要求同样摘要和完整映射。节点/来源映射不可变，先修必须无环，双向相似需显式对边，EXTENDS必须指向其先修祖先。缺失、损坏、错版本、未知字段或摘要变化抛固定`KnowledgeGraphValidationError`，不会把缺图解释为空路径或回退旧图。公开503映射与版本配置在T032/T033接入。

教材基于批准清单中的GNU C、作者维护的Open Data Structures C++0.1G和OpenDSA官方材料，只记录章节/链接与自己的元数据描述，没有复制课件。C++教材不能直接作为C代码提交。新增快排/归并的上下文明确先补递归/分治；树遍历包含显式栈和层序队列；图搜索限定访问标记、连通分量与无权BFS性质；平衡搜索树只承诺红黑树概念。

验证：`cd backend && .venv/bin/python -m pytest -q tests/test_expanded_knowledge_structure.py`，及原图/API/catalog包/path规则回归、改动Ruff/mypy。测试覆盖真实本地文件、缺失/非法JSON/符号链接来源、摘要/版本/课程资格伪造和关系错误；没有模型、网络获取、数据库或课程发布。
