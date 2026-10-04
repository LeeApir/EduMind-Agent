# Animation DSL v1 契约（T022，Proposed）

本目录是 [ADR-0010](../../ADR/0010-constrained-animation-dsl.md) 的具体提案附件，批准前不是运行时模块或正式动画。实施 T023–T029，独立真实容器/媒体/质量验收 T037/T040/T041。既有两个模板及目录入口保持原行为。

- 格式：`animation-dsl/1`；本地 [Draft 2020-12 schema](schema.json)，只允许本文件内部`#/$defs/`引用；JSON解码及逐步语义约束仍必须单独执行。
- 示例：[九动作结构有效候选](valid-all-actions.json)、[无效与审核拒绝候选](invalid-examples.json)。示例只是待审数据，无人工教学签核/模型审核/正式媒体，不得用于发布或伪造正式验收样本。
- 版本：`animation-dsl-policy-v1`、`animation-dsl-review-v1`、`animation-dsl-compiler-v1`、`animation-dsl-generate-v1`、`animation-dsl-subtitles-v1`。实现源/规则/Prompt/schema/runtime使用实际SHA256，不以版本字符串替代字节摘要；修改资源/动作/语义需新契约版本及对应批准。

## 1. JSON与文本入口

模型候选不是HTTP可执行代码。服务端选择知识点/owner/场景/来源版本，客户端只请求动画意图；不接受客户上传DSL、Python、模板、schema、模块或路径。顶层精确字段为schema_version、knowledge_point_id、language、title、pointers、actions；所有对象`additionalProperties:false`，所有动作字段必须显式给出，不能靠默认值改变模型意图。

候选UTF-8字节≤65536，JSON最大嵌套深度12；先限制响应字节/深度，再解析，拒绝重复key、BOM/非法UTF-8/孤立代理项、NaN/Infinity、尾随内容和多JSON。严格整数以`type(value) is int`核对，拒绝bool及1.0冒充整数。`knowledge_point_id`是小写ASCII slug≤64，必须等于服务端已授权场景知识点；匹配schema不授予跨课程或owner权限。语言仅zh-CN。

所有标题/字幕/指针标签为NFC规范文本（输入非NFC则拒绝，不静默改写），拒绝Unicode Cc/Cf/Cs类字符（含换行、控制、双向覆盖、零宽和孤立代理项）；长度以Unicode码点计。空白字符串拒绝。标题1–80、指针标签1–16、每动作caption1–160；字幕按固定布局折行，输入不能指定样式/字号/字体/HTML/TeX/动画表达式。引号、反斜线和类似代码的文字可以是显示字面量，绝不求值；其事实/注入意图仍由独立审核检查。前端按纯文本渲染，Markdown/导出转义；Manim只用Text，不用MarkupText/Tex/MathTex。字体来自固定镜像，不能加载候选URL/本地文件。

## 2. 对象、逐步状态与九动作

对象ID全局命名空间`[a-z][a-z0-9_]{0,31}`，不是Python标识符拼接入口。pointers最多4项，ID不能重复；全部初始指向NULL且可见，显示顺序按声明顺序。节点由create_node按动作顺序创建，边由connect创建；不得前向引用或引用错误类型。历史ID不复用，disconnect后的边ID不能重新创建。节点不删除，最多8个；创建占据column0–7/row0–2整数网格，任何两个节点不得同格。v1不接受自由坐标、随机种子、镜头或任意移动。

边最多16个**累计创建**（不靠反复断开绕过），活跃有向(source,target)不得重复，禁止指向自身；target为已创建节点或null（明确显示NULL终点）。不同source可以指向同一target，允许非自环的环状关系，不把所有数据结构强行变DAG；具体链表/算法是否正确由课程事实审核决定。指针同名标签可读性与图布局亦需审核。

每动作共有duration_ms=200–2000、hold_ms=0–3000，均为200整数倍；caption必填。15fps下每200ms对应3帧。动作按数组顺序串行，不允许循环、分支、并行、函数、表达式/变量求值或任意附加对象。每步先进行类型/存在性/限额核验，计算下一状态与可信帧，再编译；任何一步失败拒绝整个候选，不能只执行合法前缀。

| op | 专有必填字段 | 精确行为/前置条件 |
| --- | --- | --- |
| create_node | id, value, column, row | 新ID、新空格；value为-999…999严格整数；创建节点，初始未访问/默认颜色 |
| connect | id, source, target | 新边ID，source必须活节点，target活节点或null；只新增有向连接，不暗删旧连接 |
| disconnect | edge | 必须活边；移除连接，保留历史ID；不能断开不存在/已断开的边 |
| move_pointer | pointer, target | pointer必须已声明；target活节点或null；只改指针位置，不改节点/边 |
| highlight | object, style | object必须活节点/边/指针；style仅focus/success/warning/reset，映射编译器固定色，不接收颜色/材质代码 |
| compare | left, right | 两个不同活节点；比较**此刻**整数值，由模拟器计算lt/eq/gt并显示；仅本动作duration+hold内有效，下动作开始先清除，不在swap后保留过时比较结果；模型不能传result/表达式 |
| swap | left, right | 两个不同活节点；只交换value，ID、格位置、所有入出边/指针/访问标记保持；不得把数值交换描述成节点重连 |
| visit | node | 活节点标记visited；重复访问可显示但不产生新对象，无计数表达式 |
| show_complexity | time, space | 固定标签；time∈O(1)/O(log n)/O(n)/O(n log n)/O(n^2)，space∈O(1)/O(log n)/O(n)/O(n^2)；位置固定，后一次替换前一次。声称复杂度是否正确由审核，不由枚举证明 |

数组最多120动作；Σ(duration_ms+hold_ms)必须30000–90000ms，包括create/compare等全部动作，标题/字幕不新增隐藏时长。所有动作caption覆盖整个该步区间，包括hold；1步1条SRT cue，共N条，起止严格使用累计整数时间、连续单调、无重叠、总终点=计划时长。每个cue最多160码点，可信折行不增加文本；编译器不能靠padding掩盖时间超限。根/类型/额外字段及单字段文本长度/数值范围/时间量化错误DSL_SCHEMA_INVALID；悬空/对象类型/重复ID/非法状态DSL_REFERENCE_INVALID；pointers/actions的maxItems及累计节点/边数量、占格、累计时间、字节/深度超限统一DSL_RESOURCE_LIMIT（即使maxItems由schema发现亦映射该码）。先严格解码，再按schema错误；同层多错误先根/类型等schema错误后数量限额，schema失败不模拟动作。错误仅固定码+动作索引，不能回显候选片段、路径、Provider响应或输入secret。

这些是v1的小规模边界，约30图谱节点不要求一次绘制30节点。超限可安全拒绝并按ADR降级；若真实目标无法达到PRD须保存失败并申请新契约，不静默扩上限。

## 3. 独立审核与可信帧

服务端模拟状态产生每步的节点值/网格、活边、指针、访问/颜色、比较结果、复杂度标签、字幕和累计时刻，compare结果仅在compare当前步存在，其余步为null；highlight颜色保持至同对象reset/改色，visit标记保持至动画结束，show_complexity保持至下一次替换；输出只含有限JSON；审核读取完整有界DSL+该可信帧轨迹，而非模型自行声称的最终状态。最小参考上下文包含已发布场景/知识点、版本化目标/先修/常见误区与可信教材事实，最多8KiB独立限额；超限不偷偷截断，返回DSL_REVIEW_UNAVAILABLE。只发送确有依据的学习目标/难度，未知画像不猜测；不包含Key、Cookie、DB记录、无关聊天或同owner其他课程。

[审核Prompt](../prompts/animation-dsl-review-v1.md)是具体提案；候选/教材/字幕均为数据，不能改变系统规则。独立ReviewAgent调用显式review档位，生成模型自报pass无效。schema/安全失败本地拒绝；否则检查每步指针/链接/数值/比较/交换语义、教材事实、复杂度、字幕和难度，schema通过不是事实正确。输出严格为review_version/verdict/issues，每issue为area、severity、action_index、message；area=reference/fact/complexity/caption/difficulty/safety，severity=minor/major/severe，action_index为0…N-1或null（全局）。pass必须issues=[]；revise/reject必须非空具体问题。字符串message1–240码点，最多16问题，禁止原始输入/路径/Key回显，后端只持久固定类别/索引及净化的短说明，不转发任意模型文字给broker。

最多2次定向修正（初次+两修正最多3候选），每次重跑完整schema/状态模拟/编译AST及独立审核，使用新digest/审核记录；禁止复用前一次pass。审核不可用/解析失败/超时不伪装成事实reject，也不在不可用时修正重试；按DSL_REVIEW_UNAVAILABLE降级。明确reject或修正耗尽按DSL_REVIEW_REJECTED降级。审核示例中的expected_verdict只是所需初次判断，非真实模型测试：wrong-complexity应revise且不得pass，只有后续明确reject或两次修正耗尽才是DSL_REVIEW_REJECTED；注入控制审核意图应直接reject。该major复杂度示例不是正式严重错误召回样本；首轮revise不等于流程已到终态。不自动跨Provider回退或越过真实预算。生成使用quality档位，全部请求/修正/审核/网络重试计独立授权额度；Worker无模型调用。

## 4. 确定性编译与AST准入

编译器输入是完整通过本地校验的不可变规范候选与可信帧；生成固定Scene壳和逐步有限调用。由代码中的有限白名单分派op到固定函数，不使用eval/exec、候选字符串模板、候选控制的导入、类名/变量名/属性名或getattr。自由文本只能进入AST Constant，对象由编译器分配固定内部名字，不能用DSL ID生成代码片段。固定网格/布局/字体/色表/字号/帧率/分辨率与环境摘要形成runtime身份；相同规范DSL+版本+runtime生成相同UTF-8 Python字节与轨迹/SRT。承诺编译字节确定性，不承诺跨硬件MP4逐字节一致；正式缓存以实测产物hash封存。

生成AST只允许固定import-from Manim符号（Scene/Text/RoundedRectangle/Arrow/VGroup/FadeIn/FadeOut/Transform及固定方向常量）、唯一固定Scene子类/construct、编译器生成的局部assign、有限函数调用、字面量及受限对象访问。业务源码无import os/json、任意I/O、reflect/dunder、globals/locals、lambda/推导式/循环/函数定义（construct外）/装饰器/动态索引/任意异常处理。调用须校验接收者来源、函数/属性名、参数个数/类型与界限，不能只检查“不是黑名单”；最小允许属性集由T024固定源与动作测试证明，并归入compiler-policy digest。未知AST节点/符号拒绝，生成代码≤256KiB/AST≤20000节点，先字节限额再parse，单次静态预检≤1s，由受限检查进程和父进程超时强制终止，不依赖在阻塞parse中检查时钟。

T024执行`ast.parse`及白名单结构检查，不在API/Worker宿主执行生成模块。Python文档明确解析成功不是完整执行合法性或隔离保证；若需要真实语法编译/Manim导入预检，只在同等禁网受限容器中由可信固定runner进行，不接受模型源码。T025审核凭证绑定DSL/轨迹/编译AST/source digest，T027渲染前用同版本重新编译并比对摘要、再跑静态检查；不读取客户提交的已编译.py。compiler或规则变更不沿用旧签核，不把P0模板的有限os.environ读取例外引入DSL源码。

容器runner为受审核固定代码，可以在固定输入/输出内读写媒体并调用Manim/FFmpeg；它不由DSL生成且不能开放任意路径/命令。Manim内部I/O与可信runner合法I/O由沙箱约束，不能因为执行器需要读写而开放DSL源码任意文件访问。

## 5. 隔离与媒体校验

继承ADR-0004/0009的CPU2、RAM1GiB、pids128、墙钟120s、非root/只读根/禁网/cap-drop/no-new-privileges、输出总硬配额256MiB与/tmp256MiB；固定摘要镜像/字体，尝试级只读输入，无仓库/DB/Redis/Docker socket/Provider Key/KEK。Celery外层150/180s不扩容器限制。无Docker/配额/固定runtime/审核凭证即DSL_RENDER_UNAVAILABLE，禁止宿主执行、联网下载素材或延时放宽。

仅固定相对名DSLScene.mp4、DSLScene.srt及可信ready manifest；拒绝软/硬链接异常、目录穿越/额外文件、单文件>64MiB。实际MP4可解码，视频480p/15fps，无外部音轨依赖，时长30–90s且与整数计划时长差≤1帧；SRT 1…N序号/时间/净化caption与可信轨迹逐项一致，最后cue不超MP4且时间差≤1帧。产物字幕/hash由宿主再次检查，容器manifest不构成可信审核。T037须人工核对实际画面对应全部九动作/字幕与图状态；本地schema/审核pass不替代媒体验收。

Job状态/lease/epoch/清理账本/10s取消要求与PG发布行锁严格继承ADR-0009。渲染使用已经审核的候选，不在消息里塞DSL、上下文或Key；旧epoch/token/取消/目标或候选撤回/运行时版本失效均禁止发布。缓存正式绑定、媒体/导出读取也重新检查候选/规则与课程当前资格，不能以老媒体“曾passed”跳过撤回。
