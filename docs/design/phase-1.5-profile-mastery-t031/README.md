# T031 画像与掌握度

主导航接入ProfileMastery，分开展示准确当前课程原始目标、全局画像、自述来源及正式掌握度。未建立全局画像、读取失败与未知字段分别说明，不以草稿题比较/阅读替代成绩。缺来源字段标“来源未记录”；结构化字段使用人类可读标签。已存在的四类自述纠正沿原PATCH/If-Match-Profile-Version/幂等键，不新增画像算法或模型调用；递归原生表单保留对象/数组/布尔/数值语义，学生不填写JSON。原请求未知时冻结正文/键，owner域sessionStorage恢复；换身份不发送旧修改，冲突须重读。纠正不改已有课程或掌握度。

当前证据与历史修订分别呈现。T048历史API提供准确重算前revision、规则和允许的来源引用；新来源可GET准确旧attempt，复核全部绑定后展示原始输入及最新撤销/可靠性状态，失效答案/解释不显示，不用新题重评旧作答。旧来源只给允许资源/课程引用，缺失保持未知。graph/mastery版本不符时不借另一版本名称，保留节点ID并提示重读；有效/已有计算节点优先，其他节点可逐批展开，未知不显示0%。切节点、刷新和离开取消等待并丢弃迟到结果；刷新清除旧作答投影，不把旧反馈当当前事实。

实际：`pnpm --dir web exec vitest run`38文件 **273通过、0失败/跳过**，新增profile-mastery9项；typecheck/build通过；lint0错误35既有ProfileCard警告，新增及相关文件定向eslint无警告。新增场景含原始目标/来源/未知、版本化纠正、原键恢复与冻结、准确撤销原作答/转义、绑定错误/迟到结果、空与读取失败、owner变化、结构化编辑及图谱版本不符。初次类型检查修正unknown textarea类型，原生编辑使用JSON值复制避免Vue proxy不能structuredClone；没有降低类型或业务断言。

浏览器命令：`backend/.venv/bin/python /Users/apir/.agents/skills/webapp-testing/scripts/with_server.py --server 'pnpm --dir web dev --host 127.0.0.1 --port 5188' --port 5188 -- backend/.venv/bin/python docs/design/phase-1.5-profile-mastery-t031/browser_check.py`通过。真实Chromium/明确HTTP合成Mock，六宽度无横向溢出、来源/未知独立、撤销准确作答与原输入转义、原生自述纠正、刷新只GET通过；仅1次合成PATCH，无真实Provider。截图/tmp/edumind-p15-t031，1440/320已视检。前端Mock不冒充新PG/真实质量/性能成绩，后端T047/T048已经分别记录实际验收。

41批准/manifest、50历史原件及用户既有README SHA核对、工作流/diff通过。Provider0、生产catalog_only、H和旧blocked保持，无push/merge/部署。下一T032学习记录页面，阶段持续目标未完成。
