# T138 栈正常操作与拒绝边界的多场景准备

**真实 Provider 调用 0 次。** 本次交付程序材料、可编译示例及准确请求构造。测试提纲和教学正文均是本地协议夹具。真实模型提纲、真实课程和应用学习验收留待后续另定批次。

## 目标、场景与练习

目标原文为「追踪正常入栈和出栈，解释栈顶与后进先出；解释满栈为什么拒绝入栈；解释空栈为什么拒绝出栈，以及拒绝后哪些状态保持不变。」

| 场景及目标来源 | 讲解与实际演示 | 本场景练习 |
| --- | --- | --- |
| `normal` · 目标第一分句 | 沿用既有栈函数和成功主例。空栈初始化后执行 `push(3) → push(8) → pop() → push(5)`。五帧强调有效前缀、栈顶、弹出值和 LIFO，拒绝分支在本场景仅提示。 | 使用既有独立练习代码，辨认首次写入的出栈值与末次出栈后的栈顶，检查两者区别。 |
| `rejections` · 目标第二、三分句，依赖 `normal` | 同一容量 3 的栈函数，使用记录返回值并继续运行的调用者。填满后尝试 `push(9)`，随后弹空并再次 `pop()`。九帧中 f4 实际走满栈拒绝，f8 实际走空栈拒绝；两次均显示 `false`、不变的有效元素和计数、原输出值及底层槽位。空栈失败不会产生新出栈值。 | 使用不同的填充数据和被拒值，分别判断满栈后的元素数、空栈返回值、保留的调用者输出，以及两个拒绝触发的守卫。 |

两个场景的代码是同一个固定容量数组栈实现，调用者职责和观察点不同。正常场景只跟踪成功路径。拒绝场景固定使用有效的 `s/out` 指针并初始化输出变量，无效指针只在文字中说明为不支持的前提，固定容量不扩容是实现约定。可运行 C 样例用于离线核对，播放器使用程序生成的状态数据。

## 程序材料与复用

既有 `stack_course_materials.example` 默认只接受成功路径，保留原输出和拒绝语义。新增显式观察模式记录布尔返回值、调用者输出、有效元素、底层槽位、调用行及 guard 行。边界主例和边界练习的 C 调用者可编译运行并打印这组状态。程序组装练习题干、输入约定和私有答案，模型负责各场景正文和解析；本次固定的是这份课程的练习观察点。

| 独立预期 | 程序轨迹与 C 实测 |
| --- | --- |
| 满栈前后 | f3 和 f4 均为逻辑栈 `[3,8,5]`、`count=3`、底层槽位 `[3,8,5]`、`value=-99`。f4 触发第 9 行守卫，返回 `false`。 |
| 空栈前后 | f7 成功弹出 3，逻辑栈为空，底层仍为 `[3,8,5]`。f8 触发第 16 行守卫，返回 `false`，`count=0`、`value=3`、底层不变，f8 无新出栈值。 |
| 不同数据的练习 | 满栈拒绝后计数 3，空栈拒绝返回 0，调用者输出仍为 1。守卫选项 A 与 C 实际条件一致。 |

程序材料摘要 `fde1d650ce5e6267a9cc7b4c97ad66fe2414e7836705ccb02a612c34545eb0d8`。验证比较了主例及练习完整的八行 C 输出、主例逻辑状态和独立硬编码期望，也核对既有正常五帧与 T119 参考值。

## 准确请求构造

- 规划适配器读取现有规划服务的目标、来源、画像快照。基于原规划请求和本地校验，提供共享材料 ID、两个场景职责、三条原目标引文及练习目标。模型仍负责写出实际提纲、场景目的和目标描述。本批支持域要求正常操作在先、拒绝边界在后，第二场景依赖第一场景；错分目标、遗漏或倒置依赖均拒绝。
- 场景适配器读取现有场景服务的版本化输入，复用场景 ID、目标分配和准确依赖。第二场景要求第一场景的实际快照，测试用明确标记的夹具版本验证此接点。请求只开放讲解段落、事实引用和各题解析。程序合并对应代码、轨迹、题目及答案，经过原场景机械校验。拒绝跨场景解析和未绑定依赖。实际生成后的全文语义审核仍需完成。
- 当前输出是现有 Gateway 的 `StructuredRequest`，包含准确消息、Schema 与参数。真实 Provider 路由、线上格式兼容、有限预算与准入接线另行冻结。当前通用持久化服务会重建其默认请求摘要，后续要让新入口的发出请求与持久化核对使用同一适配器。本次未切换默认运行路径。现有播放器的通用栈投影展示状态和返回结果，守卫行定位保留在材料中，逐行同步显示待实际课程验收。

在仓库根目录复现三个请求和材料：

```sh
export PYTHONPATH=backend:.
pack=docs/acceptance/phase-1.5-stack-boundaries-t138
backend/.venv/bin/python -m scripts.stack_multiscene_requests materials > /tmp/stack-boundaries.json
backend/.venv/bin/python -m scripts.stack_multiscene_requests plan "$pack/planning-input.fixture.json"
backend/.venv/bin/python -m scripts.stack_multiscene_requests scene "$pack/normal-input.fixture.json"
backend/.venv/bin/python -m scripts.stack_multiscene_requests scene "$pack/rejections-input.fixture.json"
```

| 夹具预览 | 输出 SHA-256（含末尾 LF） |
| --- | --- |
| [规划输入](planning-input.fixture.json) | `8f4507c1d910c6e1d4b267820d6ae2c805e26044f2b5db5c90feda3ba4f33220` |
| [正常场景输入](normal-input.fixture.json) | `8924e230c6514230928aac6a96cc4c71bd7cde460ee187f2a6e2f770be4a499f` |
| [拒绝场景输入](rejections-input.fixture.json) | `b76cb292a6df64efb49999bfb075eed96c8b6dc8f07a83aa908fde4fecc90b8c` |

`PYTHONPATH=backend:. backend/.venv/bin/pytest -q backend/tests/test_stack_multiscene.py backend/tests/test_stack_course_profile_prompt_v2.py` 共 **5 项通过**。其中使用 Clang 按 C11、`-Wall -Wextra -Werror` 编译并运行两份拒绝样例，定向校验目标与场景、依赖、程序组装及旧请求原字节。Ruff、任务工作流和 Git 差异检查通过。T137 两课与画像对照未通过记录保留。
