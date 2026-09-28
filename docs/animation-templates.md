# MVP 0.3 动画模板注册与参数边界（T005）

仅注册 [链表插入](../data/animation_templates/linked-list-insertion.json) 和 [链表删除](../data/animation_templates/linked-list-deletion.json) 两个可信目录项；其知识点 ID 必须存在于 [知识结构](../data/knowledge_graph.yaml)。客户端的 `template_id` 只在固定映射中选取文件，不拼接路径、导入模块或生成 Python。`parameter_schema` 是白名单对象且禁止额外字段，业务校验再检查索引相对实际链表长度的界限。

| 模板 | 合法输入 | 操作边界 | 教学事实顺序 |
| --- | --- | --- | --- |
| 插入 | 0–7 个原节点、值为 -99…99 的整数、索引 0…原长度及新值 | 空链表、头/中/尾插；插后至多 8 节点 | 先让新节点 `next` 指向原后继，再接前驱或 `head` |
| 删除 | 1–8 个原节点、值为 -99…99 的整数、索引 0…原长度-1 | 单节点、头/中/尾删；空链表与越界拒绝 | 先保存目标后继，再更新前驱或 `head`，最后释放目标且不再访问 |

上述顺序根据知识结构中 `linked-list-insertion` 与 `linked-list-deletion` 的学习目标、常见误区核对，并由 [确定性回归](../backend/tests/test_animation_templates.py) 检查步骤 ID 和输入边界。清单的 `review.design_status=fact_checked` 仅表示**方案事实核对**。插入与删除模板分别在 [T006](acceptance/mvp-0.3-t006-insertion.md)、[T007](acceptance/mvp-0.3-t007-deletion.md) 完成源码、真实视频帧及字幕审核；`source_status=approved` 绑定各自的确定性步骤与 Manim 源码摘要，任一源码变化都会使加载失败。

参数经 JSON Schema 与 Python 严格整数检查后规范化为固定字段顺序；不得含个人画像、owner、URL、文件路径、代码或任意字符串。基础缓存标识以知识点、模板 ID/版本、规范化参数和语言计算，并同时纳入源码摘要、镜像/字体/渲染配置摘要、字幕和审核规则版本。`RuntimeIdentity` 必须由后续固定渲染构建提供，不能由用户请求提供。模板或任一运行版本变化都更换缓存键；完整缓存落库与媒体校验属于 T009。

[OpenAPI](api/openapi.yaml) 已同步分开插入/删除的静态输入 schema；索引相对长度的规则仍由服务端注册表执行。T006/T007 的本地构建入口用于教学审核；[T008 受限执行器](acceptance/mvp-0.3-t008-renderer.md) 将已审核源码与规范化参数编译为仅含字面量的场景，执行真实非 root、禁网、硬配额容器渲染。[T009 私有预渲染缓存](acceptance/mvp-0.3-t009-cache.md) 已准备两种基准媒体并按版本与摘要复用。正式异步 Job、owner 绑定和媒体接口仍属于 T010–T014。
