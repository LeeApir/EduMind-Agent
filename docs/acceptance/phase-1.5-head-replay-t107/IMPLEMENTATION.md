# T107 交付：已有真实头插课程接入开发主链

实际应用：[http://127.0.0.1:5197](http://127.0.0.1:5197)。本机 API 为 8177，专用数据库 `edumind_catalog_p15_t107_dev`，复用 test-only 容器 `edumind-phase1-t037-pg` 的 15437 端口。当前应用进程保留运行，已为本聊天打开的浏览器身份导入两课；该页停留在 C02 课程。首页“继续你的学习”或“学习记录”均可进入 C01/C02。

这是 **T106 既有真实候选回放**，新增 Provider 0。独立教学/接入效果评估待交接，以下为实现者验收，不冒充独立评估或真实学生学习效果。T102 仍 blocked。

## 批准与原件

[ADR0051 A—D](../../ADR/0051-head-course-development-replay.md)由用户在 `d26f237` 后明确批准，登记在[0051-approval-20261103.json](../../ADR/0051-approval-20261103.json)，绑定原 manifest SHA256 `d1d394bbd08851da8b2a813d0ddeabcb5767b2ac63005029c364debcf315fd93`。

原 ADR、manifest、提案 Schema、两个公共/私有映射和 prepare_mapping.py 全部保留原字节。原 README 描述批准前检查点，当前交付状态看本文。旧 `prepare_mapping.py --check` 包括“旧运行契约必须拒绝”的基线断言；实施后不再用它检测已变更的运行契约。运行导入器调用其纯 `map_case`，核对批准的 manifest、自身冻结字节、T106 文件 SHA/语义 digest/父稿，以及生成映射与批准附件逐值一致。

| 课程 | 原候选 | 数据库/应用身份 |
| --- | --- | --- |
| C01 | 首版 `e80a6cd201bb12add78fe74b973df432bdef544306b33c8ec63f312c3d4856f1` | 独立 owner 私有课程；一个完整场景、13帧、课程清单 v2 |
| C02 | 模型修复版 `94b98e3411cdffdce46a77387aac92d3333731e5bae340e2e886cad82596dea0`；父稿 `11733f29cba774f7273429bc20326f40eae9b38e02f727f9ebf6435df9573a51` | 独立 owner 私有课程；一个完整场景、10帧、课程清单 v2 |

v1 是现有增量协议的空大纲，v2 是全场景就绪清单；没有把提案 UUID 当成数据库 ID。实际测试课程及场景版本见 [browser-results.json](implementation-results/browser-results.json)。当前用户浏览器的实际 ID 在本机 `/tmp/edumind-t107/current-browser-import.json`，不分享会话令牌。匿名会话沿用现有两小时有效期；新浏览器身份不继承另一 owner 的私有课程。

模型原文的 45+37 处文本，以及原 candidate 文件 UTF-8、fact 绑定、parent/spec/prompt 关系保存在候选 `input_snapshot.replay`，可与 T106 原件逐字节核对。私有提案内 `status=proposal_not_imported` 是被保存的原审查附件字段，不是运行状态；运行状态来自实际 operation/ready/manifest。新 `response_json` 明确为程序映射后的候选，不冒充模型原始响应。

## 主链接线与契约差异处理

| 项目 | 实际实现 |
| --- | --- |
| 私有保存与读取 | CLI 仅允许两个固定 case 与已存在 owner，拒绝非专用 DB。复用 SnapshotRepository、FreeSceneGenerationResult、准入、presentation、ready、CAS 清单，最终 operation 成功；整次导入由调用者事务原子提交。重复导入沿用 owner+候选摘要收据，不新建课程、不覆盖后续 head。 |
| 调用审计 | 新迁移0049增加 origin_type：历史默认 model_generation/1；回放必须 existing_real_candidate_replay/0、SQL NULL usage。DB 拒绝错误来源/次数/用量组合；不新增模型 attempt、不写假 Provider 收据或假模型审核。 |
| 完整原文 | 学习前提、全部段落、逐帧 title/note、题干/解析、失败路径、生命周期和总结保留原文字。程序只增加来源标签、格式提示、展示控制、派生状态和答案；没有助手补写教学段落。 |
| 逐步讲解/作用域 | 新类型 head_insertion_replay_v1 在现有 CoursePresentation 里使用一个动作游标同步帧。保留 caller_head/local_head/p/returned、节点和原 phase；initial/caller 不显示活动 head/p，历史局部值仅在准确状态中查看。栈/动态节点与 indeterminate 原值均保留。 |
| 行高亮/判空 | 同帧 code_anchor+line 在同一组件中并排显示代码和状态，手机纵向排列、代码可横向滚动。成功判空帧复用分配后的状态、明确 line=5；不伪造新的引擎执行状态。播放/暂停/前后/重置均作用于同一游标。旧四种可视化和动作行为保留。 |
| 数组/整数答案 | 仍提交字符串，服务端按 json_integer_array/integer 严格解析。排除布尔、浮点、嵌套、非数组等，JSON 空白不影响数组相等；错误格式完整记录为不匹配并提示格式。旧 short_text 比较及既有记录不重写；新题组持久记录 free-course-typed-json-v1。 |
| 私有参考与反馈 | 页面 GET 不返回 answer_key/solution/原件全文；复用现有 Answers/CourseExercise。整组完整作答后才反馈原解析，部分作答不泄漏解析。反馈仍 provisional/course_only，无可靠答案签核或正式掌握度。 |
| 版本/权限 | 课程清单、scene_version、exercise_version、attempt 均沿既有身份绑定；跨 owner 404、缺 CSRF 403、旧清单评分409；刷新读取同一 v2/题组及原反馈，无重复写入。 |
| 开发边界 | 只有独立本机实例使用 dynamic；生产默认配置未改。开发脚本禁 Provider 工厂和外网 socket，不运行生成 Worker，并拒绝新建生成/修订/导师请求。没有新增导入 HTTP、独立播放器或调度框架。 |

## 实际检查记录

1. `backend/.venv/bin/python scripts/run_head_course_replay_dev.py --test`：专用 PG/实际 ASGI 回归 **18 passed**；[日志](implementation-results/pg-tests.txt)。含来源原件、幂等、跨 owner、私有答案、部分/完整反馈、旧版本/CSRF、严格类型比较、数据库审计约束及正常模型分支仍走原硬门。
2. 同一入口启动的实际 Chromium 四条学习流程：**C01/C02 × 1440/390px**，无 API route mock、无 pageerror，所有浏览器请求都在本机。逐帧比较 13/10 步原模型 title/note、行号、作用域、未知 next；读全段正文；播放、暂停、前后、键盘重置；四题全错/格式提示及全对、原解析；刷新后反馈100%、版本不变、attempt POST不增加，手机无页面水平溢出。[完整浏览器记录](implementation-results/browser-results.json)、[运行日志](implementation-results/browser-run.txt)。
3. `backend/.venv/bin/python scripts/run_head_course_replay_dev.py --check-migration`：0049 空库升降再升级；有回放原件时拒绝降级，前后行数/摘要相同。[结果](implementation-results/migration-results.json)。
4. `pnpm --dir web exec vitest run tests/course-visualization.spec.ts tests/responsive-accessibility.spec.ts`：**14 passed**，覆盖原可视化和减少动效/可访问性行为。`pnpm --dir web build`、相关文件 ESLint/Ruff、六个变更后端源文件 mypy、工作流及 diff 检查通过。未无故扩展到全后端/全前端或性能验收。

截图和本机失败日志摘要路径见 [local-evidence.json](implementation-results/local-evidence.json)；图片未提交 Git。桌面并排查看：[C01当前帧](/tmp/edumind-t107/browser/C01-frame-1440.png)。

开发中检查失败也保留说明：首次 PG 检查发现 JSONB 的 Python None 被写作 JSON null，违反回放要求的 SQL NULL；改为 none_as_null 后通过，旧记录未回写。正常分支测试最初误把 helper 返回 UUID 当作字典，已改为读取真实 validation 行。浏览器脚本最初用 APIRequest 读取 Secure cookie 会话，与实际浏览器的本机 cookie 行为不同；改为浏览器同源读取。随后误断言旧 HTML 的“4/4”，实际现有应用显示“匹配比例100%”，改为检查真实结果。上述均不是新的 Provider 失败或模型修复；没有修改教学文字来通过检查。首次 mypy 检查也发现动态模块/连接/返回值的可空类型，已补充显式拒绝守卫后通过。

## 重开与评估

已有服务运行时直接访问应用，勿重复占用端口。需重开时，在仓库根目录执行：

```sh
docker start edumind-phase1-t037-pg
backend/.venv/bin/python scripts/run_head_course_replay_dev.py --prepare --start
```

浏览器使用已有会话即可恢复两课。若是新的匿名身份，先打开应用建立会话，用同源 `/api/auth/session` 返回的 `user.id` 执行：

```sh
backend/.venv/bin/python scripts/run_head_course_replay_dev.py --import-owner <user.id>
```

再点首页“重新读取”。只能向已存在身份导入，不能凭课程 UUID 访问其他 owner；不把令牌放 URL、聊天或文档。脚本只检查已标记 test-only 的容器并使用专用数据库，不读取项目 `.env`，不需要 Provider Key。进程 PID/日志/测试截图在 `/tmp/edumind-t107`；可以按 PID 显式关闭本机服务，数据仍保存在专用 PG。所有运行实例均为开发检查环境，不是生产发布。

剩余差异明确如下：保留产品的整组提交后反馈，未复制旧 HTML 的逐题即时检查/独立展开参考答案；刷新恢复准确课程与反馈，播放游标重置首帧；代码只是模拟轨迹的文本，没有执行 C 或补充释放动画。caller_head/遍历枚举沿用旧 short_text 的 NFKC、大小写和空白规范化，与旧 HTML 的严格字符串比较不同；整数及数组按已批准类型排除 `1.0`/`[5.0]`，比旧 HTML 的 JavaScript number 比较严格。参考答案、题干及解析均未改写。这些没有改变原教学文本或程序事实。本次未验证新生成、其他主题、任意 C、真实学生效果或动态开放。

交评估时请从实际课程页检查连贯可学性、步骤语义/作用域/行定位、两种分配路径、输入提示与反馈、刷新版本及来源标注。不要仅凭实现者18+14项检查或T106旧独立评估代替新接入后的课程效果结论。当前无新增调用/预算或后续开发授权；完成本任务后停止，等待评估与用户决定。
