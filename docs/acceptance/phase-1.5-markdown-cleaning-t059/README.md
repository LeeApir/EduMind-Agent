# T059：代码感知Markdown清洗修复

修复r03确认的本地工程缺陷：原始合法C声明被v1全局转义改成带反斜线的代码。本次仅离线开发，不修改生成Prompt、教学标准、旧诊断输出或已签核课程；真实Provider新增0。

## 最终行为

新 `free-scene-hard-gate-v2` 使用固定 `mistune==3.4.0`、禁插件的Markdown AST区分正文与代码。对含代码的内容重新输出惰性Markdown，保留围栏、缩进及行内代码的解析后实际内容；允许规范化围栏种类、缩进语法及普通文本排版，不声称保留整个原始Markdown逐字节。围栏长度超过内容中任何同类分隔符，语言标记只保留短ASCII白名单值，不拼接任意属性。

代码外的HTML、显式链接、图片、自动尖括号链接及引用定义转成文字，不继承默认renderer重新输出引用定义的行为。对清洗结果重新解析，若出现活动link/image/HTML节点或代码载荷变化则拒绝为 `MARKDOWN_INVALID`，不裁剪内容凑通过。原完整Schema/引用/64KiB整体大小/owner和epoch围栏继续生效。

未含代码的内容保持原v1转义字节；原 `clean_markdown()` 函数保持原行为，导师链路仍使用它，本任务只改变草稿正文和私有solution的新准入。代码、题干、私有answer_key、原始模型候选不改写。

清洗结果仍是Markdown数据，**不是可信HTML**。代码中的 `<`、`>`、反斜线和HTML样例必须作为代码文字显示；当前前端保持Vue插值，没有增加v-html、任意HTML或Markdown HTML渲染入口。将来引入Markdown渲染器仍须禁raw HTML、autolink及插件，代码由渲染器转义显示，不能将此字段直接当HTML。当前jsdom组件测试证明文字中脚本/图片/链接不生成活动DOM，未宣称真实浏览器E2E或通用渲染器安全验收。

## 持久化与历史

无需迁移。已有 `(generation_result_id, rule_version)` 唯一约束及只追加触发器允许同一候选新增v2事实，原v1事实、原始响应、旧cleaned_digest和场景版本不改。实际PG验证两版本共存、v2幂等、旧行不可更新、跨owner拒绝和无新增ready/head/发布行为。测试中明确调用保留的v1实现生成旧事实，仅是隔离测试，不补写真实历史。

生产源码修复后，旧冻结r03 manifest在当前工作区应因源码摘要变化而拒绝；不能改旧manifest追溯通过。使用 `git archive b7d4b7f` 的旧源码复核旧r03，434份冻结绑定及原内容失败均符合预期，checker仍退出2。见historical-replay.json，旧准确批准/原始响应/失败不变。

r03真实原始候选零调用重放：7个正文/solution字段通过v2，代码载荷相同，原slot文件SHA保持 `2ed3d7704175404b3a0038fdb16bcafbc40a879809ed022c86480e16752e02a0`；不是重开r03、更新PG课程或取得新的真实质量通过。见r03-offline-replay.json。

## 实际验证

103个不同测试通过、0skip：

| 范围 | 结果 |
| --- | --- |
| 新AST代码/分隔符/混合恶意文本/真实声明回归 | 35 passed（含64种确定性组合） |
| 新规则实际隔离PG、v1/v2事实共存及旧行不可改 | 1 passed |
| 原T011完整准入/迁移/事务/隔离回归 | 40 passed |
| 原T013实际PG原子就绪与历史绑定回归 | 19 passed |
| 新文本安全组件及旧课堂工作区 | 8 passed（jsdom） |

实际命令与XML摘要见validation.json。PG执行器原样归档为run_pg.py（本轮以同字节 `/tmp/edumind-t059-pg.py` 执行），分别使用 `edumind_catalog_p15_t020_markdown_t059`、`edumind_catalog_p15_t011_markdown_t059`、`edumind_catalog_p15_t013_markdown_t059` 新独立库；已有诊断数据库未改。专用PG容器已恢复exited，不读取模型.env或请求Provider。

Ruff、目标源码严格mypy、前端typecheck/目标eslint、锁文件离线一致性、工作流及diff检查通过。第一次缩进代码回归发现围栏转换多出末尾换行，改为保留缩进形式后通过；未放宽断言。最初mypy发现parser返回联合类型，增加运行时AST类型检查后通过。已有Starlette BlockingPortal弃用警告1条保留。

解析器采用官方API及源码的扩展renderer机制，自定义惰性化与重新解析校验是本项目的额外约束，不把通用MarkdownRenderer当安全清洗器。参考：[Mistune API](https://mistune.lepture.com/en/latest/api.html)、锁定发行版的本地源码及backend/uv.lock中的分发摘要。

## 交接

T059交付离线修复。T038继续blocked：原r03首槽仍内容失败，其他33槽未运行；本次回放不授予真实课程质量/性能或生产动态开放。下一步如继续诊断，须基于新源码另准备准确包、新时间/请求范围及明确执行授权，禁止重启旧r03/r02。数组边界的数学写法与C表达式区分、可视化越界高亮及实际教学质量仍需在新诊断中复核，不由清洗修复自动解决。
