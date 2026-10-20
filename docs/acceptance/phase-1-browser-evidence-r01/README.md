# 三态浏览器补证（零模型调用）

复用A01/A02上轮实际隔离生成结果，以及T071/T072隔离回归库里已经存在的自动发布夹具；没有重新生成或批准课程。正式夹具不是模型通过证据，也没有完整教学节点绑定（UI如实显示历史未绑定提示）。本次只补三态显示与正式正文读取，不是完整课堂/答题/图谱旅程验收。

| 状态 | 实际UI | 正文读取 | 错误版本 | 匿名读取 |
| --- | --- | --- | --- | --- |
| [待审](pending.json) | 等待人工复核，不显示正式资源 | 404 | 404 | 401 |
| [拒绝](rejected.json) | 未通过审核，不显示正式资源 | 404 | 404 | 未在该条单独测；待审/正式已测 |
| [正式夹具](published.json) | 已审核正式资源、讲解正文 | 精确版本1为200，3场景 | 404 | 401 |

所有测试生成写接口均被只读隔离包装器403拒绝；没有Provider凭据注入、模型请求或新课程。公开API实际响应见 [formal-response.json](formal-response.json)。

修复前A02接口已返回rejected，但恢复异常被onMounted吞掉，UI仅显示初始占位。补齐拒绝恢复分支并添加回归后，用同一记录复验通过；原数据库拒绝状态不动。[修复前记录](rejected-before-fix.json)与[截图](rejected-before-fix.png)保留。相关前端14测试、类型/构建和lint通过。

[待审截图](pending.png) · [拒绝截图](rejected.png) · [正式截图](published.png)，均已实际查看。页面中旁路课堂/catalog/题目回执的403来自只读包装器范围限制，学习画像404来自已有夹具无画像；不据此声称这些模块通过，也不将这些面板的报错隐藏。正式正文显示与精确版本读取独立核验通过。

本轮首个[pending-timeout](pending-timeout.json)保存了networkidle超时及实际已出现的待审DOM。后续以最终页面URL、实际UI标识和真实API结果作为就绪门禁，networkidle未达到如实记警告，不把浏览器静默当业务正确。运行工具最初SIGTERM留下2条临时会话，已按任务时间/测试owner限定清理；新直接子进程管理器用SIGINT正常执行清理。

[清理记录](cleanup.json)：两隔离库auth_sessions均0；原实测库仍2操作/0发布，工程测试库仍32操作/11发布，数量与开始前一致。18179监听关闭；3份历史SQLite摘要均未变，见[验证记录](validation.json)。生产库/生产配置未动，Provider0。使用webapp-testing技能和原生Playwright，脚本见scripts/serve_stored_acceptance.py、check_stored_browser.py、run_stored_browser.py；使用实际构建UI与API，无Mock网络响应。

公开DOM阅读副本仅去除行末空白以通过Git格式检查；浏览器原始文本仍在local-materials保留，原始／阅读副本摘要列在validation，截图及所有断言未变。
