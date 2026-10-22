# T009：非阻塞知识点关联交接

新增私有free_course_graph_links服务，复用ADR0024批准的清单节点关联及既有仓储；不增加表、迁移或API，不调用Provider。节点关联始终是建议，不能用于评分准入。

## 行为与依据

- suggest_node_links只读取owner绑定的准确课程/计划快照，并重验既有计划摘要。按显式graph_version读取已批准版本，不采用环境中的当前版本，不创建节点。
- `free-course-exact-mention-v1`只匹配节点完整名称或完整英文ID，取最长包含匹配，避免循环队列自动变成队列、array-stack变成array；同范围同节点去重并保留来源位置。中文同义词/模糊转述不作猜测；这是一套确定性的提及建议，不能证明否定、意图或语义理解正确。生成质量和关联准确率仍须独立验收。
- 原始目标中的提及产生课程级target建议；场景title/purpose中的提及产生该场景supporting建议。全部自动结果标记planner_suggestion，不冒充user_selected。课程原目标保持原文；场景关联不改为课程目标。支持课程/各场景零/一/多节点，来源各自独立。
- evidence_refs保留匹配原文、字符区间、规则版本；目标引用课程ID及原文分域摘要，场景引用准确plan_id/digest/scene_id及字段。字段用于追溯映射理由，不是学生作答、已掌握或已核定评分证据。
- 无匹配返回no_match；未知版本或图谱发布不可用返回graph_unavailable和空关联，不静默切到另一个图谱。owner/计划不存在、快照损坏仍报身份/完整性错误，不作为可忽略图谱问题吞掉。

## 清单、历史和推荐

commit_linked_manifest从实际存储快照生成建议，然后使用现有commit_manifest在同一清单事务中绑定关联及正文、CAS切head、保存收据。复用取消/epoch/租约/期限围栏及回滚，不在历史清单上追加映射。修改映射必须产生新清单；调用者负责commit/rollback。本任务没有开放生成Worker或把私有候选改为可公开课程。

read_graph_context按准确历史课程版本返回原始目标和原关联，并单独返回recommended_paths，kind为suggestion；路径只展示图谱先修顺序及建议起点，不改变目标、不切head、不写旧路径。没有读取真实个人掌握度，因此所有路径节点标记mastery_known=false，不暴露默认0分作为学情。scoring_eligible=false表示本关联上下文本身不提供评分资格；未来可靠题组/节点核定按T003批准规则另行实施。

历史关联始终保留自己的graph_version；即使当前配置切换或历史图谱暂不可用，原关联仍可读，只有派生推荐为空。未来公开API/前端按各任务的准确投影接线，不能直接把内部evidence_refs序列化为既有NodeLink公开响应。

## 实际验证

```sh
backend/.venv/bin/python docs/acceptance/phase-1.5-graph-links-t009/run_checks.py --run-id r03 --output /tmp/edumind-p15-t009-r03
backend/.venv/bin/ruff check backend/app/services/free_course_graph_links.py backend/tests/test_free_course_graph_links.py docs/acceptance/phase-1.5-graph-links-t009/run_checks.py
(cd backend && .venv/bin/mypy app/services/free_course_graph_links.py)
python3 scripts/check_catalog_workflow.py
git diff --check
```

最终259项通过，0失败/错误/跳过：新关联30项、前置自由课程182项、旧图谱/路径47项。原始日志/XML在/tmp/edumind-p15-t009-r03；计数和原始证据摘要见results.json，过程见verification.txt。Runner仅使用已有test-only PostgreSQL容器的127.0.0.1:15437绑定及新隔离数据库；凭据不打印、不读.env、不调用真实Provider。每次使用新的run-id/输出目录。

覆盖零/一/多节点、两个批准图谱全部40个节点名称/ID、准确来源、最长匹配/完整标识符、场景去重、无匹配/图谱不可用时保留正文读取、历史稀疏计划、跨owner/计划拒绝、取消/过期/CAS/回滚/幂等及历史图谱切换。旧规划/仓储/迁移、图谱API和路径API在真实隔离PG回归；合成正文只验证存储读取，不代表教学可学性或业务E2E通过。

30份既有批准文件/5份manifest及0034–0036历史迁移保持原字节。Provider0/catalog_only/H封存/用户无关改动保持；没有真实质量/性能成绩，无push/merge/生产部署。下一T010按大纲生成场景内容仍todo，未领取。
