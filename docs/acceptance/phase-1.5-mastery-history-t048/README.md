# T048 owner掌握度修订来源

依据准确批准ADR0028，实现GET /api/mastery/nodes/{node_id}/revisions。按同owner/node的revision DESC分页，limit20/上限50，before_revision为排他正整数上界；历史节点不要求仍在当前graph，无记录返回空列表。返回历史分数/规则/摘要/准确recomputed_from_revision及白名单来源。历史分数不是当前贡献，当前GET /api/mastery继续唯一当前投影。

新来源沿LearningEvidence准确attempt与同owner/course的exercise/manifest连接，核对绑定、清单场景与版本，不猜当前head；correction沿corrects_evidence_id取得原新来源并指向被撤销的旧作答。缺失/未知协议/owner或node不符关闭引用；旧null来源仅投影允许资源/版本/课程ID，并复核owner及已有绑定一致。来源查询不SELECT原payload，索引不返回答案/解释/核定原文/Prompt/配置，原作答GET继续按最新有效性关闭错误比较。无迁移/写入/重算/Provider。

实际最终r03：新HTTP/PG5项（含正式准入、确认缺陷及原子修订两种撤销）、记录索引4、原证据准入撤销15、原API7、兼容12，**43通过、0失败/错误/跳过**，5个全新隔离PG库。检查会话/limit/slug/no-store/空历史节点、分页/旧快照不改/同owner前revision、准确旧作答引用、当前mastery回到unseen、失效GET原输入保留而答案关闭、跨owner空列表、旧无资源/有owner课程引用不公开正文、读取不新增revision。所有人工核定与模型响应均明确合成，不是真实签核或真实质量成绩。

r01的跨owner损坏历史夹具被原SQL owner外键拒绝；未绕过约束，r02保留显式IntegrityError拒绝断言，并分别测试合法入库的旧节点不匹配关闭来源，全部42通过。r03补充旧owner课程引用白名单成功路径，最终43通过。旧约束/断言/评分不改。

命令：`backend/.venv/bin/python docs/acceptance/phase-1.5-mastery-history-t048/run_checks.py --run-id r03 --output /tmp/edumind-p15-t048-r03`。原日志/XML及SHA在该目录，results.json保存摘要；Ruff5文件及strict mypy2源文件通过，runtime契约构建一致、批准设计SHA/工作流/diff通过。41批准/manifest及50历史文件完整性继续核对；用户原README不变。runtime只新增已实现的来源GET和DTO，冻结proposed文件保持原字节。

Provider0、生产catalog_only、H及旧blocked不变，无push/merge/部署。下一T031画像与掌握度页面，T032随后使用已完成T047索引，阶段持续目标未完成。
