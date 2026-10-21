# 栈越界：主要拒绝正确，附带修复断言错误，终止续测

HTTP200；完整原业务Schema、六项必检、high准确请求、用量/响应完整性通过。模型及本地为reject/code_safety/severe，技术与结构判据通过不能替代语义验收。

## 原始完整审核结果

```json
{
  "coverage": {
    "checked": [
      "action_references",
      "answer_consistency",
      "conventions",
      "example_trace",
      "objectives",
      "terminology"
    ],
    "unchecked": []
  },
  "findings": [
    {
      "anchors": [
        "a5",
        "a2"
      ],
      "category": "code_safety",
      "condition_or_counterexample": "数组a只有下标0和1。两次后置递增后top为2，代码随后执行a[top]，即读取a[2]，这是可达的越界访问。C不保证该执行有任何特定结果或正常返回，因此“由调用方获取返回值”也不能作为此代码的确定结果。",
      "impact": "代码包含未定义行为，不能可靠展示所要求的出栈返回值；预期输出对返回值的描述没有该程序行为的保证。",
      "severity": "severe"
    }
  ],
  "schema_version": "resource-review-v4",
  "scope": "unit",
  "unresolved": [
    "学生可见内容没有实现所要求的一次出栈：代码在top为2时直接读取a[top]，没有先将top减为1并读取a[top-1]，也没有明确给出有效出栈后的返回值9及top变化。练习仅检查两次入栈后的top、a[2]是否合法和是否有打印语句，没有要求学生追踪出栈过程或返回值；需补充相应讲解和过程性问题。"
  ],
  "verdict": "reject"
}
```

## 全部断言与引用核对

严重越界本身检出正确，a5源码与a2预期输出引用支持：top为2时读取长度2数组a[2]，UB不能保证数值/正常返回。但unresolved附带修复要求“先将top减为1并读取a[top-1]”错误：若先减到1再读top-1，会取a[0]=6而不是9。不能同时递减又再次使用top-1；应--top后读a[top]，或读a[top-1]后再递减。该附带断言与其后返回9矛盾，按全部断言正确的冻结规则失败，不能因主要严重拒绝正确就忽略。

两条finding引用从实际wirecatalog/record一致、resource_id/JSONpointer/content_digest/UTF8范围核验：a5支持准确源码，a2支持预期返回描述，二者没有借用邻近字段。其他缺口和题目范围说明准确。错误来自unresolved的附带修复要求，无论是否挂finding引用，仍属于本次必须核对的断言。全部明细见holdout-stack-safety-claim-review.json。

正确修复示意：原top=2时`return a[--top];`会先减为1再取a[1]=9；或先取`a[top-1]`再更新top。没有执行模型代码。模型所述“先减为1并读取a[top-1]”则取a[0]=6，不能默认为先读或按有利解释改写原输出。

## 停止与预算

本条输入15546/输出826=16372tokens，耗时10241ms。receipt `10d1c7abf1c92f0755bc8d1dd72e85d36610c65a514d00c4ad11f1aab36932f2`。实际Lee结果未预签；Codex发现失败即停止，无须把结构成功硬记语义通过。

新独立续测已发送4/5，4次完整HTTP200，前3条符合冻结预期且用户逐条确认，第4条附带修复断言错误。第5条holdout-prerequisite未预约/发送，不能复用，0自动重试/修正/回退/新候选。保留全部失败，按原候选退出条件终止本批自动审核研发，下一步讨论交付范围。正式T040未准入、catalog_only保持，不以本小诊断或人工确认补正式自动分子。
