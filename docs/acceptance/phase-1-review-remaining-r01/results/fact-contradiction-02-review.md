# 事实矛盾：核心检出成立，附带锚点精度局限待核对

用户“确认”第1条已教未考实际回答后，以首条receipt e2313fcfa32c02929b76d9f5e14b7273a05f4769df6546164f65e9d15157f44d和原proposal绑定continue，单独保存确认，不回写原receipt的历史human_confirmed=false。沿用已批准五条预算，只运行第2条一次。

原材料的讲解明确写total在i2后为16，末尾又声称sum()返回18；实际代码累加{2,5,9}，return total得到16。原回答以severe fact、reject具体识别18与16的矛盾，说明会向学生传递错误返回值，核心判据有明确证据。

锚点逐一核对：a1确实指向该讲解/markdown，包含total16与返回18两个互相矛盾的声明，是有效主证据。辅助a15实际指向练习/items/2/answer，值为F；它是合法目录ID，但不是“返回16”的直接数值证据。q3题干在其他位置提到16，不能把a15视为准确定位该声明。这里记录辅助定位精度不足，不把所有引用都算精准；也不把这个辅助不足抹掉已有a1支持的真实矛盾。没有新增另一条虚构fact finding。原finding与锚点保持原样，不修复模型原回答。整体记录为核心检出符合、辅助定位有局限、待实际人工确认。

原结构化审核：

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
        "a1",
        "a15"
      ],
      "category": "fact",
      "condition_or_counterexample": "Explanation markdown states: 累加到 total=16 之后紧接着写 “sum()返回18，不直接打印。” The array {2,5,9} sums to 2+5+9=16, and the code (`return total;`), the code's key_steps, the exercise q3 stem/explanation (返回16), and the authoritative goal/plan (返回值16) all use 16; the explanation's 18 contradicts its own preceding sentence (total=16) and every other supplied resource.",
      "impact": "The unit's central answer — the function's return value — is stated incorrectly in the student-visible explanation, directly contradicting the goal's required value 16 and the exercise feedback (q3), so learners reading the explanation before the quiz are taught the wrong result.",
      "severity": "severe"
    }
  ],
  "schema_version": "resource-review-v4",
  "scope": "unit",
  "unresolved": [],
  "verdict": "reject"
}
```

完整性六项通过：completed、单消息/单文本块、JSON/Schema有效、模型/wire与用量绑定，14136输入+1474总输出（含思考）=15610 Token，未触及8192。思考/可见拆分未知。本槽预留2.247338元，峰值未缓存用量参考0.040064元非账单；两条累计32148 Token/参考0.087324元，不是账单。

本包已用2/5、2 complete、无失败halt，剩余3条未运行；既有预算授权保留，剩余预留空间6.740266元。不运行下一条或重试；当前第二条没有human continue，人工需审视上述辅助锚点局限后再决定是否继续可达越界。没有改Prompt/Schema/low/8192/60秒或生产默认，也没有继承旧6槽。

T040正式验收仍未完成，catalog_only保持。该单例不证明所有事实/安全问题可可靠检出，且明确不宣称全部锚点精准。
