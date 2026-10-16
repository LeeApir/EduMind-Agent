# 可达越界：核心检出正确，审核自身语义问题触发整轮停止

用户“确认”第2条核心检出及辅助a15局限后，单独绑定第二条原receipt摘要continue，不抹除其已记录局限。沿用既有五条预算只运行第3条一次，原Prompt/Schema/low8192/60秒/wire不变，没有执行任何不安全C代码。

CLI返回HUMAN_CHECK_REQUIRED，完整性六项通过，结构门禁认可reject与severe code_safety。实际主发现具体指出int a[3]合法0..2、无条件源代码return a[4]可达越界/未定义行为，a6确实指/source，核心安全检出符合预期。第二条finding具体指出代码没有total/i/循环却key_steps声称这些状态；a6/a3/a4匹配实际字段，这是实际交叉矛盾。

但第三条附带fact的原论据为“其值不等于 16 且不确定”。由未定义行为只能得出不能保证返回16，不能排除某次表现为16，也不能保证正常返回；把“不保证等于”写成“不等于”是过强、缺乏依据的数值断言。此外a2/expected_output只说不打印、由调用方取得返回值，本身未声明16，不能独立作为数值矛盾证据。a1确有返回16声明且a6不安全，所以并非整条跨资源问题都不存在，但不能静默替模型改写论据并判整体干净通过。

依据：[LLVM项目对C未定义行为及越界访问的说明](https://blog.llvm.org/2011/05/what-every-c-programmer-should-know.html)。这里只核对声明能否成立，不通过运行不安全代码推断具体数值。

冻结README要求实际语义误报或漏报也停止、不能只凭路由/类别判成功。因此核心安全检出记符合，整体语义复核记未通过，在execution.lock下持久halt=ADMISSION_FAILED，原三个complete传输状态、原receipt、全部findings/锚点保持不变。没有给第三条写human continue；不允许用剩余预算/人工继续绕过本次停止。

原结构化审核（未修复）：

```json
{
  "coverage": {
    "checked": [
      "action_references",
      "answer_consistency",
      "conventions",
      "example_trace",
      "terminology"
    ],
    "unchecked": []
  },
  "findings": [
    {
      "anchors": [
        "a6"
      ],
      "category": "code_safety",
      "condition_or_counterexample": "对 `int a[3]={2,5,9};` 执行 `return a[4];`：合法下标仅为 0、1、2，`a[4]` 越界读取，且该语句在 `sum()` 的每一次调用中都必然执行（无任何前置条件可以阻止）。",
      "impact": "构成可达的越界读取/未定义行为，返回值不确定，可能崩溃或得到任意脏值；学习者会直接看到并可能运行这段不安全代码，且与“不访问 a[3]、边界内求和”的教学目标直接冲突。",
      "severity": "severe"
    },
    {
      "anchors": [
        "a6",
        "a3",
        "a4"
      ],
      "category": "fact",
      "condition_or_counterexample": "代码资源 `/source` 为 `int sum(void){int a[3]={2,5,9};return a[4];}`，其中没有循环、没有变量 total、没有下标 i；但同资源的 `/key_steps/0` 声称“total从0开始依次变为2、7、16”，`/key_steps/1` 声称“i=3时i<3为假，停止且不访问a[3]”。代码状态与所述步骤不存在对应关系。",
      "impact": "学生按 key_steps 追随时无法在代码中找到任何对应语句，形成代码与说明的自相矛盾；追踪任务的事实对象与代码不符。",
      "severity": "major"
    },
    {
      "anchors": [
        "a1",
        "a2",
        "a6"
      ],
      "category": "fact",
      "condition_or_counterexample": "解释 `/markdown` 称“sum()返回16”，代码期望输出 `/expected_output` 称“不打印；由调用方取得返回值”，但实际 `/source` 返回的是越界的 `a[4]`，其值不等于 16 且不确定。",
      "impact": "对返回值 16 的断言在实际代码上不成立（仅对未出现的累加循环成立），使解释、期望输出与代码三者在核心结论上互相矛盾。",
      "severity": "major"
    }
  ],
  "schema_version": "resource-review-v4",
  "scope": "unit",
  "unresolved": [],
  "verdict": "reject"
}
```

14134输入+1823总输出（含思考）=15957 Token，未触及8192；本槽预留2.247244元，峰值未缓存用量参考0.042852元非账单。三条累计48105 Token、参考0.130176元，保守已预留6.742538元，不是账单；剩余2槽/4.493022元不能用于恢复已halt运行。

当前3/5已运行：1已教未考用户确认；2事实矛盾用户在知悉a15局限后确认；3核心安全检出但审核自身语义不符停止。教学缺口＋越界及完整正确对照2条均未运行，不能用历史正例代填或宣称已完成完整小型审核。没有重试、第四次CLI、新冻结或Prompt/Schema/配置/生产默认修改。T040保持blocked，catalog_only保持。
