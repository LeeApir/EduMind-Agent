# r02 首槽：模型给pass，本地检查项ID门禁未过

实际模型返回 `scope=unit, verdict=pass`，没有 findings、unchecked、unresolved。
上次整单元返回 revise 的问题没有复现。接口完成、Schema、模型和实际 wire 绑定通过。

本地路由仍未通过：`coverage.checked` 返回自然语言检查描述，没有使用下面5个固定ID：
`terminology`、`conventions`、`example_trace`、`answer_consistency`、`action_references`。
对原结果离线重放得到 `needs_human / COVERAGE_INCOMPLETE`。冻结的正确对照要求自动pass，
因此 `CONTROL_NOT_AUTO_PASS` 停止该轮；r02错误分类为 INVALID_OUTPUT，账本已持久halt。

这不是本次模型指出教学内容错误：返回的描述看起来涉及了对应内容，但按原固定规则，
不能事后把自然语言映射成ID、删除未满足条件或改计为pass。尚未人工签核。

## 契约排查

运行时已把 mandatory_checks 明确放进请求；输出 Schema 的 checked.items 仍是普通字符串，
允许模型自行写描述。模型可见结构约束与本地精确ID比较仍有缺口。下一步应先零调用评估
并统一该项标识约束，不继续真实重试。不能由这一个返回证明新 Prompt 的内容审核质量。

本次 r02 仅发送1次：12416输入+151输出=12567 Token；预留2.183058元，高峰未命中
用量参考0.026040元（不是账单）。其余3槽未发。r01原2次和halt保留，不合并正式成绩。

完整证据见 [correct-unit-01.json](correct-unit-01.json)。T040仍blocked、catalog_only，
不启动T041、不沿用剩余额度自动重开。

## 模型实际完整审核结果

```json
{
  "coverage": {
    "checked": [
      "explanation markdown trace of total=2,7,16",
      "code source loop bound i<3 and no a[3] access",
      "code expected_output non-printing return value",
      "exercise q1 answer T consistency",
      "exercise q2 answer T consistency",
      "exercise q3 answer F consistency",
      "plan goal and objective sum coverage across explanation/code/exercise",
      "conventions index_base 0 and capacity 3 consistency",
      "terminology term i meaning",
      "action references to resources and anchors a3/a4",
      "example trace consistency with code and exercises"
    ],
    "unchecked": []
  },
  "findings": [],
  "schema_version": "resource-review-v4",
  "scope": "unit",
  "unresolved": [],
  "verdict": "pass"
}
```
