# 单例分散覆盖low：实际输出上限截断，按一次上限停止

本次用户批准独立1次/2.198030元后，仅执行原冻结分散覆盖low一次，未修改输入、Prompt、Schema、low或2048输出上限。

## 已证实的本次结果

- 传输分发1次，HTTP200；完整响应捕获/解码成功。
- Provider响应status=incomplete，incomplete_details.reason=max_output_tokens。
- ProviderError细分OUTPUT_TOKEN_LIMIT；总输出2048（包含思考），触及原请求上限。
- 因响应不完整，未获得完整结构化审核结果，模型pass/reject等判定与本次语义质量均未知。不是已观测的教学误报，也没有证据判定Schema本身不兼容。
- CLI通用STOPPED_OR_NOT_AUTHORIZED文案来自失败退出；本次准确授权load通过，不是用户未批准。
- 输入14218+总输出2048=16266tokens；思考/可见输出拆分未单存，不自行推算。
- 预留2.198030元；峰值未缓存用量参考0.044820元，非实际账单。
- 独立账本1条failed/INVALID_OUTPUT持久halt，1/1上限已用，剩余0。不重试、不提高上限、不进入其他样本。

## 与旧失败的关系

相同冻结wire和上限在本次触发了明确截断，这为旧失败提供线索；旧r01第三条没有留存实际细分原因/用量，本次不能替旧运行补写结果。旧账本和所有历史证据保持原样。

## 原目标及学生材料

原pass/无附带误报判据不变，但本次未得到可按其评分的审核回答。
用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。

### explanation

```json
{
  "markdown": "固定输入a={2,5,9}；sum无外部参数，返回16，不直接打印。"
}
```

### code

```json
{
  "language": "C",
  "source": "#include <stddef.h>\nint sum(void){int a[3]={2,5,9};int total=0;for(int i=0;i<3;i++)total+=a[i];return total;}",
  "expected_output": "不打印；由调用方取得返回值。",
  "key_steps": [
    "total从0开始依次变为2、7、16。",
    "i=3时i<3为假，停止且不访问a[3]。"
  ],
  "display_only": true
}
```

### exercise

```json
{
  "items": [
    {
      "id": "q1",
      "question": "[判断题] i=1这次循环结束后total=7。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "先加入a[0]=2，再加入a[1]=5，得到7。"
    },
    {
      "id": "q2",
      "question": "[判断题] i=3时停止，循环体共执行3次。仅填 T 或 F（T=正确，F=错误）",
      "answer": "T",
      "explanation": "i只在0、1、2进入循环体；i=3不满足i<3。"
    },
    {
      "id": "q3",
      "question": "[判断题] sum返回16表示它直接打印16。仅填 T 或 F（T=正确，F=错误）",
      "answer": "F",
      "explanation": "返回值交给调用方，本函数没有打印语句。"
    }
  ]
}
```

## 实际安全失败诊断

诊断记录摘要：`b4f6b6fef1fb7f65f17551ef6af31a6df04baaff73e26d4423845a92a6409df5`。仅保存允许的枚举、计数与摘要，未保存响应正文/思考或异常原文。

```json
{
  "assistant_message_count": null,
  "captured_wire_bytes": 7354,
  "captured_wire_sha256": "3f913df0a148435f30fd115f481ba392b525deb90eef1d36639370017b6ad137",
  "decode_status": "decoded",
  "decoded_response_sha256": "c579e0ce65390a750ebd9653a2f42419ad93df03b91aa35af51472ff6917a67d",
  "dispatch_is_server_receipt_proof": false,
  "error_category": "provider_protocol",
  "http_status": 200,
  "incomplete_reason": "max_output_tokens",
  "input_tokens": 14218,
  "invalid_usage_fields": [],
  "json_extra_data_kind": null,
  "json_syntax_reason": null,
  "local_gate_code": null,
  "normalized_error": "INVALID_OUTPUT",
  "output_failure_reason": "OUTPUT_TOKEN_LIMIT",
  "output_text_block_count": null,
  "output_tokens_including_reasoning": 2048,
  "provider_error_code": "INVALID_OUTPUT",
  "response_capture_complete": true,
  "response_status": "incomplete",
  "schema_keyword": null,
  "stage": "provider",
  "transport_dispatch_count": 1,
  "usage_sources": {
    "input_tokens": "provider_error",
    "output_tokens": "provider_error"
  },
  "version": "safe-failure-observation-v1"
}
```

## 停止与后续

按用户明确的一次上限，本轮到此结束。没有发起新包、修改2048或申请/消费其他预算；不以本次诊断作为T040正式质量通过。若后续决定验证更高输出上限，须另行冻结新方案和准确预算；本次不执行该工作。
