# T032 持久学习记录

LearningHistory接入真实owner课程列表、版本清单与T047四类持久记录索引，按课程分页、分类/游标分页及逐条原GET读取。原作答显示准确题组/课程版本、完整性、可靠性与贡献状态，撤回反馈关闭比较/解释，原始文本Vue转义；修订操作区分原基线与读取时当前head，不把head当该操作发布结果，未知用量不补发。导师按turn ID读取仍复用原关闭投影，旧receipt调用继续额外复核operation ID，未降低原绑定校验。读取失败与空记录分开；课程切换/owner变化/离开取消等待并忽略迟到值，owner域只保存选择与准确阅读引用，服务端索引承担实际记录，不以本机缓存代替。

本机查看数量、清单生成完整性、操作成功/部分/失败与正式掌握度分别说明，不推测已完成学习。恢复明确读取原manifest/scene，缺失不回退；主入口将这次恢复固定为following=false，防普通增量清单自动带离准确旧版本。继续生成是另一条管理入口，进入大纲不发POST；新增autoEnter选项使主动管理在刷新后仍留管理页，首次生成默认自动进入行为保留。跨课程重新建准确位置，不复制别课阅读进度。

旧协议没有完整历史列表，界面明确仅核对本机旧引用；访问前不展示旧正文，使用原owner GET及已保存publication_version，不存在不回退。未保存发布版本时明确是当前可见资源读取，不声称准确历史恢复。旧PublishedLearningWorkspace只给resources、不传CSRF/课堂回调，不自动创建课堂；生成旧资源仍由原可见性/模式控制，不迁移/重判旧评分。目录入口保留原行为。

实际：`pnpm --dir web exec vitest run`39文件 **284通过、0失败/跳过**，学习记录9项；新增大纲管理及主入口准确固定/刷新回归各1项。typecheck/build通过；全量lint0错误35既有ProfileCard警告，最终新增/相关9文件定向eslint无警告。覆盖服务端分页、原输入/撤销关闭、修订/未知/反馈/导师失效、准确旧版本不替换、跨课迟到/owner清理、空/索引失败/版本列表独立失败、刷新只GET与旧版本权限读取。

浏览器：`backend/.venv/bin/python /Users/apir/.agents/skills/webapp-testing/scripts/with_server.py --server 'pnpm --dir web dev --host 127.0.0.1 --port 5189' --port 5189 -- backend/.venv/bin/python docs/design/phase-1.5-learning-history-t032/browser_check.py`通过。真实Chromium/HTTP明确合成Mock，1440/1024/850/620/390/320无横向溢出、索引/撤销原作答转义、准确旧发布版本、显式管理及刷新留大纲、原版本固定恢复通过，POST0。旧生成资源正向示例用Mock dynamic模式以符合旧可见性语义，不是生产模式变更；catalog_only下失效/关闭由既有API及实际后端兼容检查覆盖。截图/tmp/edumind-p15-t032，1440/320已视检。不是新PG或真实质量/性能证明。

41批准/manifest与50历史原件SHA、用户既有README SHA、工作流/diff通过。无新后端/迁移/模型调用；Provider0、生产catalog_only、H和旧blocked保持，无push/merge/部署。下一T033模型设置页面，当前阶段持续目标未完成。
