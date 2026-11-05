# T109 B 局部修订：实际检查记录

本次真实单次调用使用批准的冻结入口；下列审计和浏览器检查均新增 Provider 调用 0，不重跑无关回归或构建。

| 实际入口／检查 | 结果与证据 |
| --- | --- |
| 用户 `sh /tmp/edumind-t109-b-revision-r01-live/revise.sh`，隐藏输入 Key | 唯一修订 HTTP200，3252 字节完整原件，STOP；见 attempt/body/raw/record/window |
| `backend/.venv/bin/python -I scripts/head_course_fact_revision.py --profile evidence --publish --owner c1b724d1-2bb5-49ad-aa8c-f361704e9872` | 在独立全文 pass 后，原单次入口回读原件并导入私有子课 v2；规划 0／正文生成 0／出站 0，见 published.json |
| 实际浏览器运行 `browser-reading.source.js` | 已进入应用，逐块正文／完整代码、13 帧快照及可见节点／作用域／高亮、前后步／重置／播放／暂停通过，见 browser-reading.json |
| 实际浏览器运行 `browser-feedback.source.js` | 通过真实 UI 提交 2 次，合法错答 0%、正确答案 100%；四题解析逐项显示，完整 scene／attempt 刷新相同、输入恢复、刷新新增 POST0，见 browser-feedback.json |
| `backend/.venv/bin/python docs/acceptance/phase-1.5-head-b-local-live-r01/check_application.py` | 本机开发库 READ ONLY 事务；旧 r01 failed/v1/1规划/0正文不变，新 v2 及完整存储来源 accepted，见 application-check.json |
| `backend/.venv/bin/python docs/acceptance/phase-1.5-head-b-local-live-r01/check_results.py` | 解密原件／严格响应适配／合并／完整Schema及绑定／原文仅允许差异／全文评估／浏览器证据重放通过，454项冻结及历史代码、包、其他Task不变，日志仅追加 |
| `backend/.venv/bin/python -I scripts/head_course_fact_revision.py --profile evidence --inspect` | manifest 106152…一致，Provider0，未打开新的授权 |
| 两个新审计脚本 Ruff；workflow；git diff --check／暂存区检查 | 交付前通过，未修改批准的运行源码或历史冻结文件 |

DB 检查与导入使用已有专用开发库配置 `/tmp/edumind-t108/env.json`，仅子进程加载测试数据库设置，未读项目 .env、未导出配置值、未用环境变量提供 Provider Key。首次沙箱拒绝本机网络后申请同一只读检查的执行权限，不视为产品失败或真实调用。

## 检查器自身问题记录

1. 浏览器代码路径初用 /tmp 被 MCP 文件根限制拒绝，未运行课程动作；将测试源码保存到本目录后执行。
2. 首次 13 帧检查在 f01/t0 失败：检查器误把 next 的 indeterminate 期待为英文内部值，实际组件按既有规则显示“未知（未初始化）”。[原测试源码](browser-reading.initial.source.txt) 保留；仅修正测试预期映射并从 f00 重置重跑，全部 13 帧通过。没有修改课程、组件或降低逐帧断言。
3. 新只读 DB 检查首次调用现有仓储 _operation，它会 SELECT FOR UPDATE，与显式 READ ONLY 冲突，事务回滚。检查器改为无锁 SELECT，继续保留 READ ONLY；重跑通过。运行源码和课程数据没有修改。

独立教学评估自身的旧块索引检查错误已在原 [教学报告](TEACHING-ASSESSMENT.md) 如实记录。以上检查器失败不计模型教学失败或格式恢复；原 Provider／课程失败仍保存在 r01 原目录，不改分母。

当前剩余限制：只有固定 B 支持域和两批分段执行的交付证据，不证明自由选例／普适复用／学生学习增益。原批第一次端到端无新增接点的目标曾失败；本次已批准局部修订后课程通过，不追认原批成功。已停止，无下一调用。
