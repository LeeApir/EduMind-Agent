# 8192分散覆盖单例：实际结果核对

92e4ec5冻结包获用户“批准”后，独立执行一次；CLI退出0、HUMAN_CHECK_REQUIRED。不再调用。输入、Prompt、Schema、low、判据、60秒均保持，只提高总输出上限；生产默认没有改变。

完整性：Provider完成、单助手消息/单文本块、结构化JSON及Schema、模型绑定、实际请求摘要、返回用量边界六项均通过。实际14218输入、5049总输出（含思考），未触及8192；思考/可见拆分未留存，不能推算。此前2048实测截断证据保留，这次只证明本次请求在8192内完成，不能保证其他样本都足够或回填更早未知失败原因。

语义独立核对：原目标是用C追踪{2,5,9}求和、解释下标0至2与返回16。学生可见code.key_steps写出total从0依次为2、7、16，i=3时i<3为假且不访问a[3]；题目分别检查i=1后的7、i=3退出/三次循环及返回与打印区别。代码给出正确循环，说明不打印而由调用方取得返回值。这些分散证据满足原局部目标，不要求短讲解重复全部内容、不增设动画或调用方代码要求。

模型原审核为pass；五项coverage.checked齐全，findings、unchecked、unresolved均空。与本例原判据相符，未出现附带误报。下面保存原结构化审核，未改写判定或移除finding：

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
  "findings": [],
  "schema_version": "resource-review-v4",
  "scope": "unit",
  "unresolved": [],
  "verdict": "pass"
}
```

这是一条完整正例的助手核对；真实结果尚未由用户独立签核，human_confirmed=false。没有验证教学缺口、事实、安全或混合负例，不能作为T040正式验收通过，也未修改生产配置。

预算最多1次/2.247182元；实际仅1次，用量按峰值未缓存单价参考0.068828元，非账单。账本1 complete、额度1/1已用，未设置失败halt；请求上限阻止后续预留。所有旧运行仍停止。没有重试、第二次CLI、其他案例或新的真实轮次。T040保持blocked，T041/T042未启动，catalog_only保持。
