# T037 DSL安全与动作验收

当前任务未完成：实际媒体仍须用户人工核对，不能以AI检查替代。真实Provider请求0；默认catalog_only持续，未开放动态入口、push、merge或部署。

修复范围：隔离DB按文件分配；Playwright同步线程的DB事件循环隔离；固定API幂等键满足16–128字符；Worker/交接共用同一私有测试缓存；旧固定镜像缺少CJK字体的实际缺陷改为DSL独立内容摘要镜像，并在受限容器内核验固定字体字节、精确家族与每个Text字形覆盖。无新增DSL动作/权限或放宽资源限制。构建见[固定字体运行时](../../../backend/docker/dsl/README.md)。新身份不转授旧DSL候选/媒体成绩；既有模板运行版本维持。

最新全量安全r06：288通过/0失败/0错误/0跳过，含实际Docker中文成功、旧镜像缺字体拒绝、缺字形拒绝三项回归。r05失败6项保留，原因是迁移镜像引用时启动命令遗漏固定镜像；修复并增加末尾镜像/Python/runner精确断言后，重新冻结完整r06，不用局部补测替换首败。固定媒体矩阵r05自动300/300通过；20真实视频/220逐动作帧已生成，AI抽查中文与动作显示正常。完整人工核对仍pending，不done。

固定分母保持20可信DSL（全部九动作/边界/相等关系，每样本11动作30.8秒）、100DSL槽（20冷+80暖）、100模板槽（两模板各50，20冷+80暖）、独立100缓存槽（DSL50/模板50）。明确Mock仅用于可信候选审核；PG、准备交接、Celery、Manim、HTTP、Chromium播放/MP4/SRT导出均为实际实现。无真实Provider生成/审核准确率声明，不充当T041成绩。客户端计时含playing之后的导出校验，是提交到可播放的保守上界；不冒充精确终点测量。

保留的历史执行记录：

- safety-r01：285中262通过/23失败；单DB永久政策撤销污染与T025测试迁移命名。r02初始化超时、0测试，未算通过。
- safety-r03/r04：285全部通过，无跳过。原测试PG在后续matrix-r02迁移时OOM退出（512MiB），数据/容器保持原样；新建明确label、回环15437、固定镜像的1GiB独立T037测试PG，未修改产品DB。后续安全和矩阵均按新命名空间。
- matrix-r01：100DSL失败，Playwright同步线程已有事件循环；r02环境初始化失败、300槽未运行；r03：100DSL失败，测试幂等键短于产品契约。后续修复驱动，不改固定样本/分母或产品验证规则。
- matrix-r04：自动100DSL/100模板/100缓存通过，但逐帧发现编码在MP4内的中文标题/说明是方框。完整媒体质量不通过，不请求提前人工批准。原视频/220帧/自动报告及补充visual-failure.json均保留；原自动成绩不能用于新字体版本。
- matrix-r04自动计时上界：冷DSL P95 5.524秒；DSL缓存0.393秒，模板缓存0.186秒。仅描述旧版本的播放/导出性能，不声称中文画面质量合格。

完整失败日志、协议快照、DB/测试XML、实际媒体及帧保存在ignored `local-materials/phase-1-t037`。提交仅含脱敏计数/摘要/证据路径和源文件。历史观察错误见原记录；不删除失败、不覆盖旧协议/结果、不伪造human reviewer。以下保留a90b04f断点原文供追溯，其状态/未运行表述仅适用于当时。

<details><summary>此前断点历史原文</summary>

# T037 DSL安全与动作验收断点

T037未完成，状态blocked。真实Provider请求0，动态能力仍未开放。本次准备固定协议、可信样本、真实PG/Celery/Manim/HTTP/Chromium验收脚本；现有自动检查不代替实际媒体或人工核对。

源码基线79c7e20，safety-protocol.json/matrix-protocol.json绑定当前源码、锁文件、DSL规则、编译器、模板和原签核目录。20可信DSL用例覆盖全部九动作、数值-99/99/0、相等/大小比较；每个11动作、30.8秒。独立预期最终状态：n0/n1仅交换值、连接清除、指针NULL、访问标记n1、固定规模时间/空间O(1)。验证脚本按公开动作契约检查轨迹与字幕；这些是测试输入，非新课程签核。

固定矩阵：100合法DSL槽（20未命中+80命中）；100模板槽各模板50（20未命中+80命中）；另100缓存槽，DSL50/模板50分别报告P95且逐槽≤2秒，关闭浏览器缓存。全部真实媒体矩阵尚未运行。DSL候选通过真实准备/审核绑定/交接服务，审核仅使用明确MockGateway，无真实生成/审核质量主张；渲染/PG/队列/导出仍要求产品实现及实际容器。不得在实际运行前声称脚本通过。

已运行：

- `backend/.venv/bin/python scripts/run_phase1_dsl_safety.py --run-id r01`：285测试，262通过/23失败/0跳过。首次把所有文件放一个数据库，策略撤销测试按设计永久撤销策略，污染后续文件；旧迁移拒绝测试要求T025专用数据库前缀。原log/XML/source协议保留local-materials/phase-1-t037/safety-r01，计数见results/first-safety-failure.json。
- 修复执行隔离：每文件独立全新数据库，旧迁移测试使用明确t025_t037测试命名空间；不删除撤销记录，不削弱或排除测试断言。增加初始化子进程组20秒总超时，凭据只在捕获内存/测试子进程环境，不写日志。`--run-id r02`在初始化超时，0组/0测试执行，见results/second-initialization-failure.json；未验证修复有效，不计通过。
- `backend/.venv/bin/python scripts/verify_phase1_dsl_matrix.py`：离线20用例/schema/编译AST/轨迹/字幕/九动作与100/100/100分母通过，见results/offline-plan.json。初次比较oracle用词greater/less/equal与契约gt/lt/eq不符，改正确枚举后完整重跑；未削弱关系判定。
- 新增4个Python文件Ruff/格式检查通过。实际Docker最后10秒探测超时，results/runtime-readiness.json。通过open启动现有OrbStack后曾短暂恢复r01执行；此后容器接口再次持续超时。CUA明确报告Mac锁屏，已请求用户手动解锁。不能据此推断所有测试失败源于锁屏。

记录纠正：初始化观察期间曾写“未进入测试”，执行器后续恢复并完成r01，实际XML为285/23失败；明确更正保留results/first-run-observation-correction.json，不把误观察当最终证据。r02确实未进入测试。

恢复步骤：手动解锁Mac并确认OrbStack运行；有界检查Docker/专用PG/Redis，使用新的r03运行全部安全文件，不复用旧撤销DB。完整安全组通过后执行`backend/.venv/bin/python scripts/run_phase1_dsl_matrix.py --run-id r01`，不与其他渲染并发计时。若需修改源码/规则，另冻结新一轮，保留失败；所有样本失败/未运行均分别报告。矩阵完成后才生成与真实MP4/SRT/DSL摘要绑定的逐动作人工核对材料，核对通过前不done。当前未提供媒体材料，也未请求提前批准媒体。

测试媒体/证书/完整log放ignored local-materials，不提交生成媒体或凭据。当前只提交准备成果和blocked状态，不包含Task-Completed标记；T036已完成提交保持有效。无push/merge/部署/真实Provider预算使用。

</details>

最新自动验收：matrix-r05三组各100/100；DSL冷P95保守上界5.063秒，DSL缓存0.403秒/模板缓存0.224秒，缓存逐槽≤2秒。全部计数/真实MP4/SRT/VTT/DSL/220帧摘要经verify_phase1_dsl_evidence校验；human pending、full_task_complete=false。

人工材料：`local-materials/phase-1-t037/matrix-r05/human-review/index.html`；仅回环预览 http://127.0.0.1:8177/ ，清单SHA256 `0669d0ce5a4c2dd78225bc351d09470243a4db92fd75889d1d1a33123cbb92f0`。用户按task.json T037第二条逐个核对20视频/步骤后确认；此确认仅为这些实际测试媒体的一致性，不开放动态/真实Provider预算。签核前保存blocked检查点；回复确认后核对相同摘要，记录实际用户批准，再恢复任务完成提交。
