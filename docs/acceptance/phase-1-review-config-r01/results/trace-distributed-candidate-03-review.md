# 配置对照r01：第3槽分散覆盖low尝试失败

用户确认第2条none实际结果后，仅启动第3槽一次。CLI退出2；预算账本第3条failed/INVALID_OUTPUT，运行持久halt。初始预算及绑定load均通过，不应把通用CLI文案理解成“用户未批准”。

## 已知与未知

- 已知：3次预留尝试，其中前2条complete、第3条failed，后续11槽未尝试，分散覆盖none未发。
- 没有保存本条结构化回答或failed结果receipt，无法评定模型是否给了pass/误报/错误分类。
- 本条实际发送数、HTTP状态、响应摘要、细分失败原因和token用量未持久化；发送上限1次，不能假定一定已发或一定未发。
- 当前证据不足以确认截断、Schema不兼容、服务不可用等具体根因。前次low输出1515不证明本次到达2048。
- 第3条预留2.198030元，累计预留6.594828元；失败仍消耗预留，不退款/重试。
- 仅前2条已知用量30095tokens、峰值未缓存费用参考0.069646元；第三条未知，不能把此数当全部3次总量或实际账单。

## 本条冻结目标与学生材料

原判据pass、无附带误报保持；本次没有可供对照的实际回答。
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

## 零调用代码核对

执行器在generate_structured返回后才创建含value/用量/响应摘要的receipt；只有随后assess失败才写-failed.json。当前两者均缺，且except仅归一化错误码和局部usage（尚未赋值则None）写账本。ProviderError已有细分原因和可能的usage、内存audit已有发送/状态等，但本失败路径未保存。冻结源未修改，这里只是指出证据留存缺口，不能倒推本次具体原因。

后续如修复失败可观测性，应只持久化经清洗的枚举/计数/摘要，不打印密钥、响应原文或思考文本；新执行器须重新冻结。不得在本停止运行里补发或把未知改成某一原因。

本轮保持停止，不请求human continue来绕过错误halt，不发分散none，不改生产默认/原r05停止；T040仍blocked/catalog_only。
