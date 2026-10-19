# 12份完整材料及待独立核对标签

标签由Codex起草，尚无独立人工签核；全文供Lee逐条核对。这里的标答不发送给审核模型。

## screen-complete

预期：`pass`；独立签核：pending。

原始目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

本节授权目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

教学选择：target；目标/建议/教学节点：array / array / array

完整计划（内部上下文，不算学生交付）：

```json
{
  "objectives": [
    {
      "id": "local",
      "text": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。"
    }
  ],
  "terminology": [
    {
      "term": "返回值",
      "meaning": "函数交给调用方的值，不等于打印"
    }
  ],
  "conventions": {
    "index_base": 0,
    "capacity": 3,
    "state_representation": "s为已处理元素总和，i为下一处理下标",
    "not_applicable_reasons": []
  },
  "shared_example": {
    "input_description": "a={3,8,4}",
    "initial_state": "s=0,i=0",
    "steps": [
      {
        "operation": "执行固定示例",
        "expected_state": "s为3、11、15，i=3退出",
        "expected_output": "无打印，返回15"
      }
    ]
  },
  "prerequisite_node_ids": [],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "objective_ids": [
        "local"
      ],
      "depends_on": []
    },
    {
      "role": "code",
      "scene_key": "code",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation"
      ]
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation",
        "code"
      ]
    }
  ],
  "node_id": "array",
  "graph_version": "mvp-0.2.0",
  "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
  "profile_version": null,
  "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
  "goal": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。",
  "code_language": "C",
  "schema_version": "learning-plan-v1",
  "references": [
    {
      "reference_id": "graph-node:mvp-0.2.0:array",
      "version": "mvp-0.2.0",
      "digest": "f83fd12e754fcda4124aa62b8a29203d97a897605d23dc4e37877393dcb0015d"
    }
  ]
}
```

### 学生可见 explanation

```json
{
  "markdown": "本节仅追踪一个数组求和过程，不承诺覆盖整个数组节点。函数total返回15；没有打印。开始s=0；i=0后s=3，i=1后s=11，i=2后s=15；随后i=3，i<3为假，退出，返回15。"
}
```

### 学生可见 code

```json
{
  "language": "C",
  "source": "int total(void) {\n    int a[3] = {3, 8, 4};\n    int s = 0;\n    for (int i = 0; i < 3; ++i) s += a[i];\n    return s;\n}",
  "expected_output": "无标准输出；由调用方获取返回值。",
  "key_steps": [
    "处理下标0、1、2，分别累加。",
    "在i=3时退出，返回累计和。"
  ],
  "display_only": true
}
```

### 学生可见 exercise

```json
{
  "items": [
    {
      "id": "q1",
      "question": "[判断题] i=1这一轮结束后s=11 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "初始0，先加3，再加8，得到11。"
    },
    {
      "id": "q2",
      "question": "[判断题] 退出时i=3且条件i<3为假 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "第三轮后下标递增到3，退出。"
    },
    {
      "id": "q3",
      "question": "[判断题] 此函数会将返回值打印到屏幕 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "F",
      "explanation": "没有打印语句，返回值交给调用方。"
    }
  ]
}
```

### 动作/媒体

```json
{
  "version": "teaching-actions-v1",
  "actions": [
    {
      "kind": "show_resource",
      "scene_key": "explanation",
      "resource_id": "ecc211a5-8239-5b2b-b164-8a7aa79dbcc8",
      "resource_digest": "231a158ad0859b38ed2f448c6d8eb8786fea7350cfc9666541e58cafe7f67c0b"
    },
    {
      "kind": "show_resource",
      "scene_key": "code",
      "resource_id": "cb7f6a6b-0d3c-50ca-8a06-76983abe2439",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "cb7f6a6b-0d3c-50ca-8a06-76983abe2439",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "anchor_id": "a3"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "cb7f6a6b-0d3c-50ca-8a06-76983abe2439",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "anchor_id": "a4"
    },
    {
      "kind": "show_resource",
      "scene_key": "exercise",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "exercise_id": "q1"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "exercise_id": "q2"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "exercise_id": "q3"
    }
  ],
  "anchor_catalog": [
    {
      "anchor_id": "a1",
      "resource_id": "ecc211a5-8239-5b2b-b164-8a7aa79dbcc8",
      "resource_digest": "231a158ad0859b38ed2f448c6d8eb8786fea7350cfc9666541e58cafe7f67c0b",
      "json_pointer": "/markdown",
      "start_utf8": 0,
      "end_utf8": 209
    },
    {
      "anchor_id": "a2",
      "resource_id": "cb7f6a6b-0d3c-50ca-8a06-76983abe2439",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/expected_output",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a3",
      "resource_id": "cb7f6a6b-0d3c-50ca-8a06-76983abe2439",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/key_steps/0",
      "start_utf8": 0,
      "end_utf8": 39
    },
    {
      "anchor_id": "a4",
      "resource_id": "cb7f6a6b-0d3c-50ca-8a06-76983abe2439",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/key_steps/1",
      "start_utf8": 0,
      "end_utf8": 36
    },
    {
      "anchor_id": "a5",
      "resource_id": "cb7f6a6b-0d3c-50ca-8a06-76983abe2439",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/language",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a6",
      "resource_id": "cb7f6a6b-0d3c-50ca-8a06-76983abe2439",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/source",
      "start_utf8": 0,
      "end_utf8": 117
    },
    {
      "anchor_id": "a7",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a8",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/explanation",
      "start_utf8": 0,
      "end_utf8": 41
    },
    {
      "anchor_id": "a9",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a10",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/question",
      "start_utf8": 0,
      "end_utf8": 80
    },
    {
      "anchor_id": "a11",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a12",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/explanation",
      "start_utf8": 0,
      "end_utf8": 40
    },
    {
      "anchor_id": "a13",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a14",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/question",
      "start_utf8": 0,
      "end_utf8": 85
    },
    {
      "anchor_id": "a15",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a16",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/explanation",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a17",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a18",
      "resource_id": "7ca24568-7aa8-57b5-8aa6-403b1365b8b0",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/question",
      "start_utf8": 0,
      "end_utf8": 94
    }
  ],
  "digest": "1cf2ee048d17abd63d37b224c7c356a8e1419ef6a177685b943ccc45286715b1"
}
```

本单元未承诺动画，动作不当成已播放动画。

### 标签理由/核对要求

- 所有必检ID齐全，findings/unchecked/unresolved均为空；无附带误报。

- 核对所有实际陈述与引用，不只检查主错误；任何附带不实意见不通过。

## screen-distributed

预期：`pass`；独立签核：pending。

原始目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

本节授权目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

教学选择：target；目标/建议/教学节点：array / array / array

完整计划（内部上下文，不算学生交付）：

```json
{
  "objectives": [
    {
      "id": "local",
      "text": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。"
    }
  ],
  "terminology": [
    {
      "term": "返回值",
      "meaning": "函数交给调用方的值，不等于打印"
    }
  ],
  "conventions": {
    "index_base": 0,
    "capacity": 3,
    "state_representation": "s为已处理元素总和，i为下一处理下标",
    "not_applicable_reasons": []
  },
  "shared_example": {
    "input_description": "a={3,8,4}",
    "initial_state": "s=0,i=0",
    "steps": [
      {
        "operation": "执行固定示例",
        "expected_state": "s为3、11、15，i=3退出",
        "expected_output": "无打印，返回15"
      }
    ]
  },
  "prerequisite_node_ids": [],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "objective_ids": [
        "local"
      ],
      "depends_on": []
    },
    {
      "role": "code",
      "scene_key": "code",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation"
      ]
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation",
        "code"
      ]
    }
  ],
  "node_id": "array",
  "graph_version": "mvp-0.2.0",
  "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
  "profile_version": null,
  "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
  "goal": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。",
  "code_language": "C",
  "schema_version": "learning-plan-v1",
  "references": [
    {
      "reference_id": "graph-node:mvp-0.2.0:array",
      "version": "mvp-0.2.0",
      "digest": "f83fd12e754fcda4124aa62b8a29203d97a897605d23dc4e37877393dcb0015d"
    }
  ]
}
```

### 学生可见 explanation

```json
{
  "markdown": "total求和数组{3,8,4}，返回15，不打印。过程见代码关键步骤与练习解析。"
}
```

### 学生可见 code

```json
{
  "language": "C",
  "source": "int total(void) {\n    int a[3] = {3, 8, 4};\n    int s = 0;\n    for (int i = 0; i < 3; ++i) s += a[i];\n    return s;\n}",
  "expected_output": "无标准输出；由调用方获取返回值。",
  "key_steps": [
    "开始s=0；i=0后s=3，i=1后s=11，i=2后s=15；随后i=3，i<3为假，退出，返回15。"
  ],
  "display_only": true
}
```

### 学生可见 exercise

```json
{
  "items": [
    {
      "id": "q1",
      "question": "[判断题] i=1这一轮结束后s=11 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "初始0，先加3，再加8，得到11。"
    },
    {
      "id": "q2",
      "question": "[判断题] 退出时i=3且条件i<3为假 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "第三轮后下标递增到3，退出。"
    },
    {
      "id": "q3",
      "question": "[判断题] 此函数会将返回值打印到屏幕 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "F",
      "explanation": "没有打印语句，返回值交给调用方。"
    }
  ]
}
```

### 动作/媒体

```json
{
  "version": "teaching-actions-v1",
  "actions": [
    {
      "kind": "show_resource",
      "scene_key": "explanation",
      "resource_id": "69fd10be-ce94-5a1c-b9ef-d9af0069c3dd",
      "resource_digest": "0d01e6ddcf3af4096839a1643665a897866e593f5334fd0ce5ef1de7acc64cdd"
    },
    {
      "kind": "show_resource",
      "scene_key": "code",
      "resource_id": "3295f589-817c-5d12-b391-e318a6d8a055",
      "resource_digest": "46fb9dd59f44b0fda40148086f1c999024cf854cc6ac94f4e98901aba4badc18"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "3295f589-817c-5d12-b391-e318a6d8a055",
      "resource_digest": "46fb9dd59f44b0fda40148086f1c999024cf854cc6ac94f4e98901aba4badc18",
      "anchor_id": "a3"
    },
    {
      "kind": "show_resource",
      "scene_key": "exercise",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "exercise_id": "q1"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "exercise_id": "q2"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "exercise_id": "q3"
    }
  ],
  "anchor_catalog": [
    {
      "anchor_id": "a1",
      "resource_id": "69fd10be-ce94-5a1c-b9ef-d9af0069c3dd",
      "resource_digest": "0d01e6ddcf3af4096839a1643665a897866e593f5334fd0ce5ef1de7acc64cdd",
      "json_pointer": "/markdown",
      "start_utf8": 0,
      "end_utf8": 95
    },
    {
      "anchor_id": "a2",
      "resource_id": "3295f589-817c-5d12-b391-e318a6d8a055",
      "resource_digest": "46fb9dd59f44b0fda40148086f1c999024cf854cc6ac94f4e98901aba4badc18",
      "json_pointer": "/expected_output",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a3",
      "resource_id": "3295f589-817c-5d12-b391-e318a6d8a055",
      "resource_digest": "46fb9dd59f44b0fda40148086f1c999024cf854cc6ac94f4e98901aba4badc18",
      "json_pointer": "/key_steps/0",
      "start_utf8": 0,
      "end_utf8": 94
    },
    {
      "anchor_id": "a4",
      "resource_id": "3295f589-817c-5d12-b391-e318a6d8a055",
      "resource_digest": "46fb9dd59f44b0fda40148086f1c999024cf854cc6ac94f4e98901aba4badc18",
      "json_pointer": "/language",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a5",
      "resource_id": "3295f589-817c-5d12-b391-e318a6d8a055",
      "resource_digest": "46fb9dd59f44b0fda40148086f1c999024cf854cc6ac94f4e98901aba4badc18",
      "json_pointer": "/source",
      "start_utf8": 0,
      "end_utf8": 117
    },
    {
      "anchor_id": "a6",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a7",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/explanation",
      "start_utf8": 0,
      "end_utf8": 41
    },
    {
      "anchor_id": "a8",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a9",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/question",
      "start_utf8": 0,
      "end_utf8": 80
    },
    {
      "anchor_id": "a10",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a11",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/explanation",
      "start_utf8": 0,
      "end_utf8": 40
    },
    {
      "anchor_id": "a12",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a13",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/question",
      "start_utf8": 0,
      "end_utf8": 85
    },
    {
      "anchor_id": "a14",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a15",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/explanation",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a16",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a17",
      "resource_id": "f15a9c61-258a-5189-9c15-4a9f98bd1675",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/question",
      "start_utf8": 0,
      "end_utf8": 94
    }
  ],
  "digest": "4f80507ce4135a772ad0fc1d2251dde11413d9c03bba97391859e0e81c8e0b4c"
}
```

本单元未承诺动画，动作不当成已播放动画。

### 标签理由/核对要求

- 所有必检ID齐全，findings/unchecked/unresolved均为空；无附带误报。

- 核对所有实际陈述与引用，不只检查主错误；任何附带不实意见不通过。

## screen-teaching-gap

预期：`needs_human`；独立签核：pending。

原始目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

本节授权目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

教学选择：target；目标/建议/教学节点：array / array / array

完整计划（内部上下文，不算学生交付）：

```json
{
  "objectives": [
    {
      "id": "local",
      "text": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。"
    }
  ],
  "terminology": [
    {
      "term": "返回值",
      "meaning": "函数交给调用方的值，不等于打印"
    }
  ],
  "conventions": {
    "index_base": 0,
    "capacity": 3,
    "state_representation": "s为已处理元素总和，i为下一处理下标",
    "not_applicable_reasons": []
  },
  "shared_example": {
    "input_description": "a={3,8,4}",
    "initial_state": "s=0,i=0",
    "steps": [
      {
        "operation": "执行固定示例",
        "expected_state": "s为3、11、15，i=3退出",
        "expected_output": "无打印，返回15"
      }
    ]
  },
  "prerequisite_node_ids": [],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "objective_ids": [
        "local"
      ],
      "depends_on": []
    },
    {
      "role": "code",
      "scene_key": "code",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation"
      ]
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation",
        "code"
      ]
    }
  ],
  "node_id": "array",
  "graph_version": "mvp-0.2.0",
  "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
  "profile_version": null,
  "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
  "goal": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。",
  "code_language": "C",
  "schema_version": "learning-plan-v1",
  "references": [
    {
      "reference_id": "graph-node:mvp-0.2.0:array",
      "version": "mvp-0.2.0",
      "digest": "f83fd12e754fcda4124aa62b8a29203d97a897605d23dc4e37877393dcb0015d"
    }
  ]
}
```

### 学生可见 explanation

```json
{
  "markdown": "total处理数组{3,8,4}，无打印语句。"
}
```

### 学生可见 code

```json
{
  "language": "C",
  "source": "int total(void) {\n    int a[3] = {3, 8, 4};\n    int s = 0;\n    for (int i = 0; i < 3; ++i) s += a[i];\n    return s;\n}",
  "expected_output": "无标准输出；由调用方获取返回值。",
  "key_steps": [
    "按实现运行。"
  ],
  "display_only": true
}
```

### 学生可见 exercise

```json
{
  "items": [
    {
      "id": "q1",
      "question": "[判断题] 3+8+4=15 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "算术总和是15。"
    },
    {
      "id": "q2",
      "question": "[判断题] 数组长度是3 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "声明长度3。"
    },
    {
      "id": "q3",
      "question": "[判断题] 函数中存在打印语句 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "F",
      "explanation": "没有打印语句。"
    }
  ]
}
```

### 动作/媒体

```json
{
  "version": "teaching-actions-v1",
  "actions": [
    {
      "kind": "show_resource",
      "scene_key": "explanation",
      "resource_id": "03b0aacb-3cda-59d9-b5e3-1085861ce375",
      "resource_digest": "1b1177a5b5a0f5a05e99d6e6aae2d704e460ff82ec89c45b8b21e19e2eae4614"
    },
    {
      "kind": "show_resource",
      "scene_key": "code",
      "resource_id": "c4159993-15bf-52cd-abe2-de733c3a8a81",
      "resource_digest": "483bea2d7c4d59473597ac6edb9afab80c99b276dd66a0fc7ad6c1a49410b945"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "c4159993-15bf-52cd-abe2-de733c3a8a81",
      "resource_digest": "483bea2d7c4d59473597ac6edb9afab80c99b276dd66a0fc7ad6c1a49410b945",
      "anchor_id": "a3"
    },
    {
      "kind": "show_resource",
      "scene_key": "exercise",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "exercise_id": "q1"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "exercise_id": "q2"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "exercise_id": "q3"
    }
  ],
  "anchor_catalog": [
    {
      "anchor_id": "a1",
      "resource_id": "03b0aacb-3cda-59d9-b5e3-1085861ce375",
      "resource_digest": "1b1177a5b5a0f5a05e99d6e6aae2d704e460ff82ec89c45b8b21e19e2eae4614",
      "json_pointer": "/markdown",
      "start_utf8": 0,
      "end_utf8": 45
    },
    {
      "anchor_id": "a2",
      "resource_id": "c4159993-15bf-52cd-abe2-de733c3a8a81",
      "resource_digest": "483bea2d7c4d59473597ac6edb9afab80c99b276dd66a0fc7ad6c1a49410b945",
      "json_pointer": "/expected_output",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a3",
      "resource_id": "c4159993-15bf-52cd-abe2-de733c3a8a81",
      "resource_digest": "483bea2d7c4d59473597ac6edb9afab80c99b276dd66a0fc7ad6c1a49410b945",
      "json_pointer": "/key_steps/0",
      "start_utf8": 0,
      "end_utf8": 18
    },
    {
      "anchor_id": "a4",
      "resource_id": "c4159993-15bf-52cd-abe2-de733c3a8a81",
      "resource_digest": "483bea2d7c4d59473597ac6edb9afab80c99b276dd66a0fc7ad6c1a49410b945",
      "json_pointer": "/language",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a5",
      "resource_id": "c4159993-15bf-52cd-abe2-de733c3a8a81",
      "resource_digest": "483bea2d7c4d59473597ac6edb9afab80c99b276dd66a0fc7ad6c1a49410b945",
      "json_pointer": "/source",
      "start_utf8": 0,
      "end_utf8": 117
    },
    {
      "anchor_id": "a6",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/0/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a7",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/0/explanation",
      "start_utf8": 0,
      "end_utf8": 20
    },
    {
      "anchor_id": "a8",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/0/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a9",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/0/question",
      "start_utf8": 0,
      "end_utf8": 63
    },
    {
      "anchor_id": "a10",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/1/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a11",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/1/explanation",
      "start_utf8": 0,
      "end_utf8": 16
    },
    {
      "anchor_id": "a12",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/1/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a13",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/1/question",
      "start_utf8": 0,
      "end_utf8": 71
    },
    {
      "anchor_id": "a14",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/2/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a15",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/2/explanation",
      "start_utf8": 0,
      "end_utf8": 21
    },
    {
      "anchor_id": "a16",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/2/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a17",
      "resource_id": "824ab689-1eb5-520b-b445-53557ea0836d",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/2/question",
      "start_utf8": 0,
      "end_utf8": 82
    }
  ],
  "digest": "9f24bdd3132ac3b98e0a02eeb7998158cb437ce4f3478f572cdc86167888b68c"
}
```

本单元未承诺动画，动作不当成已播放动画。

### 标签理由/核对要求

- 具体说明学生可见关键状态/退出教学不足，以及题目未考查过程；内部计划不算交付。

- 核对所有实际陈述与引用，不只检查主错误；任何附带不实意见不通过。

## screen-assessment-gap

预期：`needs_human`；独立签核：pending。

原始目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

本节授权目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

教学选择：target；目标/建议/教学节点：array / array / array

完整计划（内部上下文，不算学生交付）：

```json
{
  "objectives": [
    {
      "id": "local",
      "text": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。"
    }
  ],
  "terminology": [
    {
      "term": "返回值",
      "meaning": "函数交给调用方的值，不等于打印"
    }
  ],
  "conventions": {
    "index_base": 0,
    "capacity": 3,
    "state_representation": "s为已处理元素总和，i为下一处理下标",
    "not_applicable_reasons": []
  },
  "shared_example": {
    "input_description": "a={3,8,4}",
    "initial_state": "s=0,i=0",
    "steps": [
      {
        "operation": "执行固定示例",
        "expected_state": "s为3、11、15，i=3退出",
        "expected_output": "无打印，返回15"
      }
    ]
  },
  "prerequisite_node_ids": [],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "objective_ids": [
        "local"
      ],
      "depends_on": []
    },
    {
      "role": "code",
      "scene_key": "code",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation"
      ]
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation",
        "code"
      ]
    }
  ],
  "node_id": "array",
  "graph_version": "mvp-0.2.0",
  "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
  "profile_version": null,
  "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
  "goal": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。",
  "code_language": "C",
  "schema_version": "learning-plan-v1",
  "references": [
    {
      "reference_id": "graph-node:mvp-0.2.0:array",
      "version": "mvp-0.2.0",
      "digest": "f83fd12e754fcda4124aa62b8a29203d97a897605d23dc4e37877393dcb0015d"
    }
  ]
}
```

### 学生可见 explanation

```json
{
  "markdown": "本节仅追踪一个数组求和过程，不承诺覆盖整个数组节点。函数total返回15；没有打印。开始s=0；i=0后s=3，i=1后s=11，i=2后s=15；随后i=3，i<3为假，退出，返回15。"
}
```

### 学生可见 code

```json
{
  "language": "C",
  "source": "int total(void) {\n    int a[3] = {3, 8, 4};\n    int s = 0;\n    for (int i = 0; i < 3; ++i) s += a[i];\n    return s;\n}",
  "expected_output": "无标准输出；由调用方获取返回值。",
  "key_steps": [
    "处理下标0、1、2，分别累加。",
    "在i=3时退出，返回累计和。"
  ],
  "display_only": true
}
```

### 学生可见 exercise

```json
{
  "items": [
    {
      "id": "q1",
      "question": "[判断题] 3+8+4=15 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "算术总和15。"
    },
    {
      "id": "q2",
      "question": "[判断题] 数组长度是3 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "长度3。"
    },
    {
      "id": "q3",
      "question": "[判断题] 函数打印15 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "F",
      "explanation": "函数不打印。"
    }
  ]
}
```

### 动作/媒体

```json
{
  "version": "teaching-actions-v1",
  "actions": [
    {
      "kind": "show_resource",
      "scene_key": "explanation",
      "resource_id": "08fde277-cd35-5be1-841d-458a72bc7234",
      "resource_digest": "231a158ad0859b38ed2f448c6d8eb8786fea7350cfc9666541e58cafe7f67c0b"
    },
    {
      "kind": "show_resource",
      "scene_key": "code",
      "resource_id": "6309dba2-b452-515d-b0a8-681f236983e8",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "6309dba2-b452-515d-b0a8-681f236983e8",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "anchor_id": "a3"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "6309dba2-b452-515d-b0a8-681f236983e8",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "anchor_id": "a4"
    },
    {
      "kind": "show_resource",
      "scene_key": "exercise",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f",
      "exercise_id": "q1"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f",
      "exercise_id": "q2"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f",
      "exercise_id": "q3"
    }
  ],
  "anchor_catalog": [
    {
      "anchor_id": "a1",
      "resource_id": "08fde277-cd35-5be1-841d-458a72bc7234",
      "resource_digest": "231a158ad0859b38ed2f448c6d8eb8786fea7350cfc9666541e58cafe7f67c0b",
      "json_pointer": "/markdown",
      "start_utf8": 0,
      "end_utf8": 209
    },
    {
      "anchor_id": "a2",
      "resource_id": "6309dba2-b452-515d-b0a8-681f236983e8",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/expected_output",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a3",
      "resource_id": "6309dba2-b452-515d-b0a8-681f236983e8",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/key_steps/0",
      "start_utf8": 0,
      "end_utf8": 39
    },
    {
      "anchor_id": "a4",
      "resource_id": "6309dba2-b452-515d-b0a8-681f236983e8",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/key_steps/1",
      "start_utf8": 0,
      "end_utf8": 36
    },
    {
      "anchor_id": "a5",
      "resource_id": "6309dba2-b452-515d-b0a8-681f236983e8",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/language",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a6",
      "resource_id": "6309dba2-b452-515d-b0a8-681f236983e8",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/source",
      "start_utf8": 0,
      "end_utf8": 117
    },
    {
      "anchor_id": "a7",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f",
      "json_pointer": "/items/0/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a8",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f",
      "json_pointer": "/items/0/explanation",
      "start_utf8": 0,
      "end_utf8": 17
    },
    {
      "anchor_id": "a9",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f",
      "json_pointer": "/items/0/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a10",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f",
      "json_pointer": "/items/0/question",
      "start_utf8": 0,
      "end_utf8": 63
    },
    {
      "anchor_id": "a11",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f",
      "json_pointer": "/items/1/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a12",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f",
      "json_pointer": "/items/1/explanation",
      "start_utf8": 0,
      "end_utf8": 10
    },
    {
      "anchor_id": "a13",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f",
      "json_pointer": "/items/1/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a14",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f",
      "json_pointer": "/items/1/question",
      "start_utf8": 0,
      "end_utf8": 71
    },
    {
      "anchor_id": "a15",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f",
      "json_pointer": "/items/2/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a16",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f",
      "json_pointer": "/items/2/explanation",
      "start_utf8": 0,
      "end_utf8": 18
    },
    {
      "anchor_id": "a17",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f",
      "json_pointer": "/items/2/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a18",
      "resource_id": "d1c59a63-4042-5254-9e5a-ae7a4ac91274",
      "resource_digest": "80da7eb0182bb75e56599934a658acd9f6886a2daea48bc2dac97ee014a3638f",
      "json_pointer": "/items/2/question",
      "start_utf8": 0,
      "end_utf8": 69
    }
  ],
  "digest": "88d9548cdb1b02eeba0d774afb8d150e24aa1f120a87a5d58ac05bc10ef7d36c"
}
```

本单元未承诺动画，动作不当成已播放动画。

### 标签理由/核对要求

- 已教状态与退出边界，准确指出仅测最终值/长度而未测过程；不得声称未教。

- 核对所有实际陈述与引用，不只检查主错误；任何附带不实意见不通过。

## screen-fact

预期：`reject`；独立签核：pending。

原始目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

本节授权目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

教学选择：target；目标/建议/教学节点：array / array / array

完整计划（内部上下文，不算学生交付）：

```json
{
  "objectives": [
    {
      "id": "local",
      "text": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。"
    }
  ],
  "terminology": [
    {
      "term": "返回值",
      "meaning": "函数交给调用方的值，不等于打印"
    }
  ],
  "conventions": {
    "index_base": 0,
    "capacity": 3,
    "state_representation": "s为已处理元素总和，i为下一处理下标",
    "not_applicable_reasons": []
  },
  "shared_example": {
    "input_description": "a={3,8,4}",
    "initial_state": "s=0,i=0",
    "steps": [
      {
        "operation": "执行固定示例",
        "expected_state": "s为3、11、15，i=3退出",
        "expected_output": "无打印，返回15"
      }
    ]
  },
  "prerequisite_node_ids": [],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "objective_ids": [
        "local"
      ],
      "depends_on": []
    },
    {
      "role": "code",
      "scene_key": "code",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation"
      ]
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation",
        "code"
      ]
    }
  ],
  "node_id": "array",
  "graph_version": "mvp-0.2.0",
  "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
  "profile_version": null,
  "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
  "goal": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。",
  "code_language": "C",
  "schema_version": "learning-plan-v1",
  "references": [
    {
      "reference_id": "graph-node:mvp-0.2.0:array",
      "version": "mvp-0.2.0",
      "digest": "f83fd12e754fcda4124aa62b8a29203d97a897605d23dc4e37877393dcb0015d"
    }
  ]
}
```

### 学生可见 explanation

```json
{
  "markdown": "本节仅追踪一个数组求和过程，不承诺覆盖整个数组节点。函数total返回17；没有打印。开始s=0；i=0后s=3，i=1后s=11，i=2后s=15；随后i=3，i<3为假，退出，返回15。"
}
```

### 学生可见 code

```json
{
  "language": "C",
  "source": "int total(void) {\n    int a[3] = {3, 8, 4};\n    int s = 0;\n    for (int i = 0; i < 3; ++i) s += a[i];\n    return s;\n}",
  "expected_output": "无标准输出；由调用方获取返回值。",
  "key_steps": [
    "处理下标0、1、2，分别累加。",
    "在i=3时退出，返回累计和。"
  ],
  "display_only": true
}
```

### 学生可见 exercise

```json
{
  "items": [
    {
      "id": "q1",
      "question": "[判断题] i=1这一轮结束后s=11 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "初始0，先加3，再加8，得到11。"
    },
    {
      "id": "q2",
      "question": "[判断题] 退出时i=3且条件i<3为假 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "第三轮后下标递增到3，退出。"
    },
    {
      "id": "q3",
      "question": "[判断题] 此函数会将返回值打印到屏幕 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "F",
      "explanation": "没有打印语句，返回值交给调用方。"
    }
  ]
}
```

### 动作/媒体

```json
{
  "version": "teaching-actions-v1",
  "actions": [
    {
      "kind": "show_resource",
      "scene_key": "explanation",
      "resource_id": "1b0a2b80-7cb8-5d12-9f17-9093bfc75618",
      "resource_digest": "a06fdbd962e113de359a8de717c502d37a847e35773ff55736cc642c8bff43fe"
    },
    {
      "kind": "show_resource",
      "scene_key": "code",
      "resource_id": "921dbabd-3f73-5630-b32f-613772ebfc1d",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "921dbabd-3f73-5630-b32f-613772ebfc1d",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "anchor_id": "a3"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "921dbabd-3f73-5630-b32f-613772ebfc1d",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "anchor_id": "a4"
    },
    {
      "kind": "show_resource",
      "scene_key": "exercise",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "exercise_id": "q1"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "exercise_id": "q2"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "exercise_id": "q3"
    }
  ],
  "anchor_catalog": [
    {
      "anchor_id": "a1",
      "resource_id": "1b0a2b80-7cb8-5d12-9f17-9093bfc75618",
      "resource_digest": "a06fdbd962e113de359a8de717c502d37a847e35773ff55736cc642c8bff43fe",
      "json_pointer": "/markdown",
      "start_utf8": 0,
      "end_utf8": 209
    },
    {
      "anchor_id": "a2",
      "resource_id": "921dbabd-3f73-5630-b32f-613772ebfc1d",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/expected_output",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a3",
      "resource_id": "921dbabd-3f73-5630-b32f-613772ebfc1d",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/key_steps/0",
      "start_utf8": 0,
      "end_utf8": 39
    },
    {
      "anchor_id": "a4",
      "resource_id": "921dbabd-3f73-5630-b32f-613772ebfc1d",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/key_steps/1",
      "start_utf8": 0,
      "end_utf8": 36
    },
    {
      "anchor_id": "a5",
      "resource_id": "921dbabd-3f73-5630-b32f-613772ebfc1d",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/language",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a6",
      "resource_id": "921dbabd-3f73-5630-b32f-613772ebfc1d",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/source",
      "start_utf8": 0,
      "end_utf8": 117
    },
    {
      "anchor_id": "a7",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a8",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/explanation",
      "start_utf8": 0,
      "end_utf8": 41
    },
    {
      "anchor_id": "a9",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a10",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/question",
      "start_utf8": 0,
      "end_utf8": 80
    },
    {
      "anchor_id": "a11",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a12",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/explanation",
      "start_utf8": 0,
      "end_utf8": 40
    },
    {
      "anchor_id": "a13",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a14",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/question",
      "start_utf8": 0,
      "end_utf8": 85
    },
    {
      "anchor_id": "a15",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a16",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/explanation",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a17",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a18",
      "resource_id": "06e76569-babc-5b2b-8834-190ea2c2f81d",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/question",
      "start_utf8": 0,
      "end_utf8": 94
    }
  ],
  "digest": "ee06e0216cac29cd6bc91a57709eb85f2fd251fb003e2fb5751c4e211e27082c"
}
```

本单元未承诺动画，动作不当成已播放动画。

### 标签理由/核对要求

- 指出返回值声明与实际程序矛盾，引用声明和程序；不得编造其他缺陷。

- 核对所有实际陈述与引用，不只检查主错误；任何附带不实意见不通过。

## screen-safety

预期：`reject`；独立签核：pending。

原始目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

本节授权目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

教学选择：target；目标/建议/教学节点：array / array / array

完整计划（内部上下文，不算学生交付）：

```json
{
  "objectives": [
    {
      "id": "local",
      "text": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。"
    }
  ],
  "terminology": [
    {
      "term": "返回值",
      "meaning": "函数交给调用方的值，不等于打印"
    }
  ],
  "conventions": {
    "index_base": 0,
    "capacity": 3,
    "state_representation": "s为已处理元素总和，i为下一处理下标",
    "not_applicable_reasons": []
  },
  "shared_example": {
    "input_description": "a={3,8,4}",
    "initial_state": "s=0,i=0",
    "steps": [
      {
        "operation": "执行固定示例",
        "expected_state": "s为3、11、15，i=3退出",
        "expected_output": "无打印，返回15"
      }
    ]
  },
  "prerequisite_node_ids": [],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "objective_ids": [
        "local"
      ],
      "depends_on": []
    },
    {
      "role": "code",
      "scene_key": "code",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation"
      ]
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation",
        "code"
      ]
    }
  ],
  "node_id": "array",
  "graph_version": "mvp-0.2.0",
  "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
  "profile_version": null,
  "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
  "goal": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。",
  "code_language": "C",
  "schema_version": "learning-plan-v1",
  "references": [
    {
      "reference_id": "graph-node:mvp-0.2.0:array",
      "version": "mvp-0.2.0",
      "digest": "f83fd12e754fcda4124aa62b8a29203d97a897605d23dc4e37877393dcb0015d"
    }
  ]
}
```

### 学生可见 explanation

```json
{
  "markdown": "total返回15，不打印。开始s=0；i=0后s=3，i=1后s=11，i=2后s=15；随后i=3，i<3为假，退出，返回15。配套extra是另一个可直接调用的取值函数。"
}
```

### 学生可见 code

```json
{
  "language": "C",
  "source": "int total(void) {\n    int a[3]={3,8,4}; int s=0;\n    for(int i=0;i<3;++i) s+=a[i];\n    return s;\n}\nint extra(void) { int a[3]={3,8,4}; return a[5]; }",
  "expected_output": "无标准输出；由调用方获取返回值。",
  "key_steps": [
    "处理下标0、1、2，分别累加。",
    "在i=3时退出，返回累计和。"
  ],
  "display_only": true
}
```

### 学生可见 exercise

```json
{
  "items": [
    {
      "id": "q1",
      "question": "[判断题] i=1这一轮结束后s=11 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "初始0，先加3，再加8，得到11。"
    },
    {
      "id": "q2",
      "question": "[判断题] 退出时i=3且条件i<3为假 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "第三轮后下标递增到3，退出。"
    },
    {
      "id": "q3",
      "question": "[判断题] 此函数会将返回值打印到屏幕 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "F",
      "explanation": "没有打印语句，返回值交给调用方。"
    }
  ]
}
```

### 动作/媒体

```json
{
  "version": "teaching-actions-v1",
  "actions": [
    {
      "kind": "show_resource",
      "scene_key": "explanation",
      "resource_id": "f44c7cfd-9ed9-523b-926b-2310f839b1af",
      "resource_digest": "524196f2c96bc3461b652a7fa302d40cba00d1e96df524c305b4c7bd19bb4f09"
    },
    {
      "kind": "show_resource",
      "scene_key": "code",
      "resource_id": "58616ef9-84bb-57c7-a947-ae6d1da98f15",
      "resource_digest": "ed5c81060603e8f5668f120c9a366e5d995ee2ae5800f8234db03775b8086354"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "58616ef9-84bb-57c7-a947-ae6d1da98f15",
      "resource_digest": "ed5c81060603e8f5668f120c9a366e5d995ee2ae5800f8234db03775b8086354",
      "anchor_id": "a3"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "58616ef9-84bb-57c7-a947-ae6d1da98f15",
      "resource_digest": "ed5c81060603e8f5668f120c9a366e5d995ee2ae5800f8234db03775b8086354",
      "anchor_id": "a4"
    },
    {
      "kind": "show_resource",
      "scene_key": "exercise",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "exercise_id": "q1"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "exercise_id": "q2"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "exercise_id": "q3"
    }
  ],
  "anchor_catalog": [
    {
      "anchor_id": "a1",
      "resource_id": "f44c7cfd-9ed9-523b-926b-2310f839b1af",
      "resource_digest": "524196f2c96bc3461b652a7fa302d40cba00d1e96df524c305b4c7bd19bb4f09",
      "json_pointer": "/markdown",
      "start_utf8": 0,
      "end_utf8": 178
    },
    {
      "anchor_id": "a2",
      "resource_id": "58616ef9-84bb-57c7-a947-ae6d1da98f15",
      "resource_digest": "ed5c81060603e8f5668f120c9a366e5d995ee2ae5800f8234db03775b8086354",
      "json_pointer": "/expected_output",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a3",
      "resource_id": "58616ef9-84bb-57c7-a947-ae6d1da98f15",
      "resource_digest": "ed5c81060603e8f5668f120c9a366e5d995ee2ae5800f8234db03775b8086354",
      "json_pointer": "/key_steps/0",
      "start_utf8": 0,
      "end_utf8": 39
    },
    {
      "anchor_id": "a4",
      "resource_id": "58616ef9-84bb-57c7-a947-ae6d1da98f15",
      "resource_digest": "ed5c81060603e8f5668f120c9a366e5d995ee2ae5800f8234db03775b8086354",
      "json_pointer": "/key_steps/1",
      "start_utf8": 0,
      "end_utf8": 36
    },
    {
      "anchor_id": "a5",
      "resource_id": "58616ef9-84bb-57c7-a947-ae6d1da98f15",
      "resource_digest": "ed5c81060603e8f5668f120c9a366e5d995ee2ae5800f8234db03775b8086354",
      "json_pointer": "/language",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a6",
      "resource_id": "58616ef9-84bb-57c7-a947-ae6d1da98f15",
      "resource_digest": "ed5c81060603e8f5668f120c9a366e5d995ee2ae5800f8234db03775b8086354",
      "json_pointer": "/source",
      "start_utf8": 0,
      "end_utf8": 149
    },
    {
      "anchor_id": "a7",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a8",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/explanation",
      "start_utf8": 0,
      "end_utf8": 41
    },
    {
      "anchor_id": "a9",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a10",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/question",
      "start_utf8": 0,
      "end_utf8": 80
    },
    {
      "anchor_id": "a11",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a12",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/explanation",
      "start_utf8": 0,
      "end_utf8": 40
    },
    {
      "anchor_id": "a13",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a14",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/question",
      "start_utf8": 0,
      "end_utf8": 85
    },
    {
      "anchor_id": "a15",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a16",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/explanation",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a17",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a18",
      "resource_id": "10ba6d8a-e404-51a6-bf53-133156a48e53",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/question",
      "start_utf8": 0,
      "end_utf8": 94
    }
  ],
  "digest": "bc40bce59a0ad969a06cc0adf0d8f142fa01373a6176676edd00df2506bc0d18"
}
```

本单元未承诺动画，动作不当成已播放动画。

### 标签理由/核对要求

- 指出实际可达越界及精确长度/索引；不得从未定义行为推出必然不等于某个数值。

- 核对所有实际陈述与引用，不只检查主错误；任何附带不实意见不通过。

## screen-mixed

预期：`reject`；独立签核：pending。

原始目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

本节授权目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

教学选择：target；目标/建议/教学节点：array / array / array

完整计划（内部上下文，不算学生交付）：

```json
{
  "objectives": [
    {
      "id": "local",
      "text": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。"
    }
  ],
  "terminology": [
    {
      "term": "返回值",
      "meaning": "函数交给调用方的值，不等于打印"
    }
  ],
  "conventions": {
    "index_base": 0,
    "capacity": 3,
    "state_representation": "s为已处理元素总和，i为下一处理下标",
    "not_applicable_reasons": []
  },
  "shared_example": {
    "input_description": "a={3,8,4}",
    "initial_state": "s=0,i=0",
    "steps": [
      {
        "operation": "执行固定示例",
        "expected_state": "s为3、11、15，i=3退出",
        "expected_output": "无打印，返回15"
      }
    ]
  },
  "prerequisite_node_ids": [],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "objective_ids": [
        "local"
      ],
      "depends_on": []
    },
    {
      "role": "code",
      "scene_key": "code",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation"
      ]
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation",
        "code"
      ]
    }
  ],
  "node_id": "array",
  "graph_version": "mvp-0.2.0",
  "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
  "profile_version": null,
  "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
  "goal": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。",
  "code_language": "C",
  "schema_version": "learning-plan-v1",
  "references": [
    {
      "reference_id": "graph-node:mvp-0.2.0:array",
      "version": "mvp-0.2.0",
      "digest": "f83fd12e754fcda4124aa62b8a29203d97a897605d23dc4e37877393dcb0015d"
    }
  ]
}
```

### 学生可见 explanation

```json
{
  "markdown": "本节用total处理数组{3,8,4}，无打印语句。"
}
```

### 学生可见 code

```json
{
  "language": "C",
  "source": "int total(void) {\n    int a[3] = {3, 8, 4};\n    return a[5];\n}",
  "expected_output": "无标准输出；由调用方获取返回值。",
  "key_steps": [
    "按实现运行。"
  ],
  "display_only": true
}
```

### 学生可见 exercise

```json
{
  "items": [
    {
      "id": "q1",
      "question": "[判断题] 3+8+4=15 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "算术总和是15。"
    },
    {
      "id": "q2",
      "question": "[判断题] 数组长度是3 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "声明长度3。"
    },
    {
      "id": "q3",
      "question": "[判断题] 函数中存在打印语句 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "F",
      "explanation": "没有打印语句。"
    }
  ]
}
```

### 动作/媒体

```json
{
  "version": "teaching-actions-v1",
  "actions": [
    {
      "kind": "show_resource",
      "scene_key": "explanation",
      "resource_id": "8ebcf1cf-6d2e-518a-b687-f363addd8732",
      "resource_digest": "7fc025dd0052a62132396270a55c37c4c7ac6ffaf6bd93027bf949e3e5dddc14"
    },
    {
      "kind": "show_resource",
      "scene_key": "code",
      "resource_id": "284aa074-dac7-5601-990b-eb6708bcf2ec",
      "resource_digest": "e553640610a450c99ec39dfd62b627f9c3806fe10d6c8fe6d8db5edfc8bf9a51"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "284aa074-dac7-5601-990b-eb6708bcf2ec",
      "resource_digest": "e553640610a450c99ec39dfd62b627f9c3806fe10d6c8fe6d8db5edfc8bf9a51",
      "anchor_id": "a3"
    },
    {
      "kind": "show_resource",
      "scene_key": "exercise",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "exercise_id": "q1"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "exercise_id": "q2"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "exercise_id": "q3"
    }
  ],
  "anchor_catalog": [
    {
      "anchor_id": "a1",
      "resource_id": "8ebcf1cf-6d2e-518a-b687-f363addd8732",
      "resource_digest": "7fc025dd0052a62132396270a55c37c4c7ac6ffaf6bd93027bf949e3e5dddc14",
      "json_pointer": "/markdown",
      "start_utf8": 0,
      "end_utf8": 54
    },
    {
      "anchor_id": "a2",
      "resource_id": "284aa074-dac7-5601-990b-eb6708bcf2ec",
      "resource_digest": "e553640610a450c99ec39dfd62b627f9c3806fe10d6c8fe6d8db5edfc8bf9a51",
      "json_pointer": "/expected_output",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a3",
      "resource_id": "284aa074-dac7-5601-990b-eb6708bcf2ec",
      "resource_digest": "e553640610a450c99ec39dfd62b627f9c3806fe10d6c8fe6d8db5edfc8bf9a51",
      "json_pointer": "/key_steps/0",
      "start_utf8": 0,
      "end_utf8": 18
    },
    {
      "anchor_id": "a4",
      "resource_id": "284aa074-dac7-5601-990b-eb6708bcf2ec",
      "resource_digest": "e553640610a450c99ec39dfd62b627f9c3806fe10d6c8fe6d8db5edfc8bf9a51",
      "json_pointer": "/language",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a5",
      "resource_id": "284aa074-dac7-5601-990b-eb6708bcf2ec",
      "resource_digest": "e553640610a450c99ec39dfd62b627f9c3806fe10d6c8fe6d8db5edfc8bf9a51",
      "json_pointer": "/source",
      "start_utf8": 0,
      "end_utf8": 62
    },
    {
      "anchor_id": "a6",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/0/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a7",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/0/explanation",
      "start_utf8": 0,
      "end_utf8": 20
    },
    {
      "anchor_id": "a8",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/0/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a9",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/0/question",
      "start_utf8": 0,
      "end_utf8": 63
    },
    {
      "anchor_id": "a10",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/1/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a11",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/1/explanation",
      "start_utf8": 0,
      "end_utf8": 16
    },
    {
      "anchor_id": "a12",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/1/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a13",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/1/question",
      "start_utf8": 0,
      "end_utf8": 71
    },
    {
      "anchor_id": "a14",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/2/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a15",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/2/explanation",
      "start_utf8": 0,
      "end_utf8": 21
    },
    {
      "anchor_id": "a16",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/2/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a17",
      "resource_id": "d053dc65-3186-5bbb-a4a5-01ace0159477",
      "resource_digest": "d2603c4b9ef28793ba96cafe4a7a03f85697aedb72f6f1fccf26df445fcfd0f8",
      "json_pointer": "/items/2/question",
      "start_utf8": 0,
      "end_utf8": 82
    }
  ],
  "digest": "2a01643fbb24b2280d7f725127edf675e785aa7d9ff6bb842db91426dcfbbb5d"
}
```

本单元未承诺动画，动作不当成已播放动画。

### 标签理由/核对要求

- 指出实际可达越界及精确长度/索引；不得从未定义行为推出必然不等于某个数值。

- 程序未实现原始目标承诺的求和循环；这是实际交付缺口，须具体说明，不能误记为附带误报。

- 具体说明学生可见关键状态/退出教学不足，以及题目未考查过程；内部计划不算交付。

- 核对所有实际陈述与引用，不只检查主错误；任何附带不实意见不通过。

## screen-full-node-promise

预期：`needs_human`；独立签核：pending。

原始目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

本节授权目标：用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。

教学选择：target；目标/建议/教学节点：array / array / array

完整计划（内部上下文，不算学生交付）：

```json
{
  "objectives": [
    {
      "id": "local",
      "text": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。"
    }
  ],
  "terminology": [
    {
      "term": "返回值",
      "meaning": "函数交给调用方的值，不等于打印"
    }
  ],
  "conventions": {
    "index_base": 0,
    "capacity": 3,
    "state_representation": "s为已处理元素总和，i为下一处理下标",
    "not_applicable_reasons": []
  },
  "shared_example": {
    "input_description": "a={3,8,4}",
    "initial_state": "s=0,i=0",
    "steps": [
      {
        "operation": "执行固定示例",
        "expected_state": "s为3、11、15，i=3退出",
        "expected_output": "无打印，返回15"
      }
    ]
  },
  "prerequisite_node_ids": [],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "objective_ids": [
        "local"
      ],
      "depends_on": []
    },
    {
      "role": "code",
      "scene_key": "code",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation"
      ]
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation",
        "code"
      ]
    }
  ],
  "node_id": "array",
  "graph_version": "mvp-0.2.0",
  "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
  "profile_version": null,
  "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
  "goal": "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。",
  "code_language": "C",
  "schema_version": "learning-plan-v1",
  "references": [
    {
      "reference_id": "graph-node:mvp-0.2.0:array",
      "version": "mvp-0.2.0",
      "digest": "f83fd12e754fcda4124aa62b8a29203d97a897605d23dc4e37877393dcb0015d"
    }
  ]
}
```

### 学生可见 explanation

```json
{
  "markdown": "函数total返回15；没有打印。开始s=0；i=0后s=3，i=1后s=11，i=2后s=15；随后i=3，i<3为假，退出，返回15。本节承诺完整覆盖数组基本操作，包括插入和删除。"
}
```

### 学生可见 code

```json
{
  "language": "C",
  "source": "int total(void) {\n    int a[3] = {3, 8, 4};\n    int s = 0;\n    for (int i = 0; i < 3; ++i) s += a[i];\n    return s;\n}",
  "expected_output": "无标准输出；由调用方获取返回值。",
  "key_steps": [
    "处理下标0、1、2，分别累加。",
    "在i=3时退出，返回累计和。"
  ],
  "display_only": true
}
```

### 学生可见 exercise

```json
{
  "items": [
    {
      "id": "q1",
      "question": "[判断题] i=1这一轮结束后s=11 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "初始0，先加3，再加8，得到11。"
    },
    {
      "id": "q2",
      "question": "[判断题] 退出时i=3且条件i<3为假 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "第三轮后下标递增到3，退出。"
    },
    {
      "id": "q3",
      "question": "[判断题] 此函数会将返回值打印到屏幕 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "F",
      "explanation": "没有打印语句，返回值交给调用方。"
    }
  ]
}
```

### 动作/媒体

```json
{
  "version": "teaching-actions-v1",
  "actions": [
    {
      "kind": "show_resource",
      "scene_key": "explanation",
      "resource_id": "97abea81-d837-58ff-96ff-75365484b552",
      "resource_digest": "672ab1c0ebadad573cfdfa60afeb3d3b3f356faed457c010c55b2c02f85468fa"
    },
    {
      "kind": "show_resource",
      "scene_key": "code",
      "resource_id": "daeab082-c24e-5132-8f71-f8d51f2ef88e",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "daeab082-c24e-5132-8f71-f8d51f2ef88e",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "anchor_id": "a3"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "daeab082-c24e-5132-8f71-f8d51f2ef88e",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "anchor_id": "a4"
    },
    {
      "kind": "show_resource",
      "scene_key": "exercise",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "exercise_id": "q1"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "exercise_id": "q2"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "exercise_id": "q3"
    }
  ],
  "anchor_catalog": [
    {
      "anchor_id": "a1",
      "resource_id": "97abea81-d837-58ff-96ff-75365484b552",
      "resource_digest": "672ab1c0ebadad573cfdfa60afeb3d3b3f356faed457c010c55b2c02f85468fa",
      "json_pointer": "/markdown",
      "start_utf8": 0,
      "end_utf8": 200
    },
    {
      "anchor_id": "a2",
      "resource_id": "daeab082-c24e-5132-8f71-f8d51f2ef88e",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/expected_output",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a3",
      "resource_id": "daeab082-c24e-5132-8f71-f8d51f2ef88e",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/key_steps/0",
      "start_utf8": 0,
      "end_utf8": 39
    },
    {
      "anchor_id": "a4",
      "resource_id": "daeab082-c24e-5132-8f71-f8d51f2ef88e",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/key_steps/1",
      "start_utf8": 0,
      "end_utf8": 36
    },
    {
      "anchor_id": "a5",
      "resource_id": "daeab082-c24e-5132-8f71-f8d51f2ef88e",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/language",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a6",
      "resource_id": "daeab082-c24e-5132-8f71-f8d51f2ef88e",
      "resource_digest": "229b73713cd20cd33b3919fd5af8b16556481758f363f3e7c1bda5941539e3e9",
      "json_pointer": "/source",
      "start_utf8": 0,
      "end_utf8": 117
    },
    {
      "anchor_id": "a7",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a8",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/explanation",
      "start_utf8": 0,
      "end_utf8": 41
    },
    {
      "anchor_id": "a9",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a10",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/0/question",
      "start_utf8": 0,
      "end_utf8": 80
    },
    {
      "anchor_id": "a11",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a12",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/explanation",
      "start_utf8": 0,
      "end_utf8": 40
    },
    {
      "anchor_id": "a13",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a14",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/1/question",
      "start_utf8": 0,
      "end_utf8": 85
    },
    {
      "anchor_id": "a15",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a16",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/explanation",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a17",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a18",
      "resource_id": "1ec5b551-776b-5e50-8bc8-dff40b6a385f",
      "resource_digest": "c10c4673cb1364b3f59ddc52b7629468c57c81ad0d4dd396cc5d9b88701b7af0",
      "json_pointer": "/items/2/question",
      "start_utf8": 0,
      "end_utf8": 94
    }
  ],
  "digest": "6e9b11111f68fb4d9d8217baffe2a689bf3a6b4055c814177788a34fc0cc0ba6"
}
```

本单元未承诺动画，动作不当成已播放动画。

### 标签理由/核对要求

- 指出显式完整基本操作承诺中的插入/删除没有交付，不能只按局部求和目标放行；不将缺教学编造为fact。

- 核对所有实际陈述与引用，不只检查主错误；任何附带不实意见不通过。

## holdout-stack-complete

预期：`pass`；独立签核：pending。

原始目标：用C展示容量2的栈依次入栈6、9和一次出栈，明确追踪top和返回值，并用题目检查操作过程。

本节授权目标：用C展示容量2的栈依次入栈6、9和一次出栈，明确追踪top和返回值，并用题目检查操作过程。

教学选择：target；目标/建议/教学节点：stack / stack / stack

完整计划（内部上下文，不算学生交付）：

```json
{
  "objectives": [
    {
      "id": "local",
      "text": "用C展示容量2的栈依次入栈6、9和一次出栈，明确追踪top和返回值，并用题目检查操作过程。"
    }
  ],
  "terminology": [
    {
      "term": "返回值",
      "meaning": "函数交给调用方的值，不等于打印"
    }
  ],
  "conventions": {
    "index_base": 0,
    "capacity": 2,
    "state_representation": "top为已存元素数",
    "not_applicable_reasons": []
  },
  "shared_example": {
    "input_description": "入栈6、9",
    "initial_state": "top=0",
    "steps": [
      {
        "operation": "执行固定示例",
        "expected_state": "top为1、2、1",
        "expected_output": "无打印，返回9"
      }
    ]
  },
  "prerequisite_node_ids": [],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "objective_ids": [
        "local"
      ],
      "depends_on": []
    },
    {
      "role": "code",
      "scene_key": "code",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation"
      ]
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation",
        "code"
      ]
    }
  ],
  "node_id": "stack",
  "graph_version": "mvp-0.2.0",
  "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
  "profile_version": null,
  "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
  "goal": "用C展示容量2的栈依次入栈6、9和一次出栈，明确追踪top和返回值，并用题目检查操作过程。",
  "code_language": "C",
  "schema_version": "learning-plan-v1",
  "references": [
    {
      "reference_id": "graph-node:mvp-0.2.0:stack",
      "version": "mvp-0.2.0",
      "digest": "fcd31b8e716614bb18a06dcac7e20afbfb1fa4dccccc1871a6391bc96ce121b0"
    }
  ]
}
```

### 学生可见 explanation

```json
{
  "markdown": "定长栈只做这两次入栈、一次出栈，不是可任意调用的通用接口。top从0到1到2，出栈先减到1，取a[1]=9，返回9，无打印；这组有限操作始终在容量2内。"
}
```

### 学生可见 code

```json
{
  "language": "C",
  "source": "int top_value(void) {\n    int a[2] = {6, 9};\n    int top = 0;\n    a[top++] = 6;\n    a[top++] = 9;\n    return a[--top];\n}",
  "expected_output": "无标准输出；由调用方获取返回值。",
  "key_steps": [
    "top表示元素数，也是下一写入位置；先减后取符合后进先出。"
  ],
  "display_only": true
}
```

### 学生可见 exercise

```json
{
  "items": [
    {
      "id": "q1",
      "question": "[判断题] 第二次入栈后top=2 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "两次递增得到2。"
    },
    {
      "id": "q2",
      "question": "[判断题] 出栈先令top=1再取a[1] 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "前置递减先执行。"
    },
    {
      "id": "q3",
      "question": "[判断题] 此次出栈返回最早放入的6 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "F",
      "explanation": "返回后放入的9。"
    }
  ]
}
```

### 动作/媒体

```json
{
  "version": "teaching-actions-v1",
  "actions": [
    {
      "kind": "show_resource",
      "scene_key": "explanation",
      "resource_id": "e63309ad-12bd-5f87-a744-e85873a5e8f5",
      "resource_digest": "fbf9411b90c51c86ec81f38f161e7e0fa88f9d565d4ad5d11ad47818ce94708c"
    },
    {
      "kind": "show_resource",
      "scene_key": "code",
      "resource_id": "a93f06e5-2820-5160-8939-e9527a01a700",
      "resource_digest": "d2773e879760ea0e7c2ce77242908e7b85bdb4ad0a68c0df2856386d5299f02c"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "a93f06e5-2820-5160-8939-e9527a01a700",
      "resource_digest": "d2773e879760ea0e7c2ce77242908e7b85bdb4ad0a68c0df2856386d5299f02c",
      "anchor_id": "a3"
    },
    {
      "kind": "show_resource",
      "scene_key": "exercise",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "exercise_id": "q1"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "exercise_id": "q2"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "exercise_id": "q3"
    }
  ],
  "anchor_catalog": [
    {
      "anchor_id": "a1",
      "resource_id": "e63309ad-12bd-5f87-a744-e85873a5e8f5",
      "resource_digest": "fbf9411b90c51c86ec81f38f161e7e0fa88f9d565d4ad5d11ad47818ce94708c",
      "json_pointer": "/markdown",
      "start_utf8": 0,
      "end_utf8": 198
    },
    {
      "anchor_id": "a2",
      "resource_id": "a93f06e5-2820-5160-8939-e9527a01a700",
      "resource_digest": "d2773e879760ea0e7c2ce77242908e7b85bdb4ad0a68c0df2856386d5299f02c",
      "json_pointer": "/expected_output",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a3",
      "resource_id": "a93f06e5-2820-5160-8939-e9527a01a700",
      "resource_digest": "d2773e879760ea0e7c2ce77242908e7b85bdb4ad0a68c0df2856386d5299f02c",
      "json_pointer": "/key_steps/0",
      "start_utf8": 0,
      "end_utf8": 81
    },
    {
      "anchor_id": "a4",
      "resource_id": "a93f06e5-2820-5160-8939-e9527a01a700",
      "resource_digest": "d2773e879760ea0e7c2ce77242908e7b85bdb4ad0a68c0df2856386d5299f02c",
      "json_pointer": "/language",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a5",
      "resource_id": "a93f06e5-2820-5160-8939-e9527a01a700",
      "resource_digest": "d2773e879760ea0e7c2ce77242908e7b85bdb4ad0a68c0df2856386d5299f02c",
      "json_pointer": "/source",
      "start_utf8": 0,
      "end_utf8": 120
    },
    {
      "anchor_id": "a6",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/0/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a7",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/0/explanation",
      "start_utf8": 0,
      "end_utf8": 22
    },
    {
      "anchor_id": "a8",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/0/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a9",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/0/question",
      "start_utf8": 0,
      "end_utf8": 78
    },
    {
      "anchor_id": "a10",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/1/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a11",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/1/explanation",
      "start_utf8": 0,
      "end_utf8": 24
    },
    {
      "anchor_id": "a12",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/1/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a13",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/1/question",
      "start_utf8": 0,
      "end_utf8": 82
    },
    {
      "anchor_id": "a14",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/2/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a15",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/2/explanation",
      "start_utf8": 0,
      "end_utf8": 22
    },
    {
      "anchor_id": "a16",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/2/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a17",
      "resource_id": "18afccaf-57b9-5f08-9113-b1c90a7f29bd",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/2/question",
      "start_utf8": 0,
      "end_utf8": 89
    }
  ],
  "digest": "2a438bca50b7b9e8d3e028d24398e194d2650eb89c1008f1b078f9e2c0a0b802"
}
```

本单元未承诺动画，动作不当成已播放动画。

### 标签理由/核对要求

- 所有必检ID齐全，findings/unchecked/unresolved均为空；无附带误报。

- 核对所有实际陈述与引用，不只检查主错误；任何附带不实意见不通过。

## holdout-stack-fact

预期：`reject`；独立签核：pending。

原始目标：用C展示容量2的栈依次入栈6、9和一次出栈，明确追踪top和返回值，并用题目检查操作过程。

本节授权目标：用C展示容量2的栈依次入栈6、9和一次出栈，明确追踪top和返回值，并用题目检查操作过程。

教学选择：target；目标/建议/教学节点：stack / stack / stack

完整计划（内部上下文，不算学生交付）：

```json
{
  "objectives": [
    {
      "id": "local",
      "text": "用C展示容量2的栈依次入栈6、9和一次出栈，明确追踪top和返回值，并用题目检查操作过程。"
    }
  ],
  "terminology": [
    {
      "term": "返回值",
      "meaning": "函数交给调用方的值，不等于打印"
    }
  ],
  "conventions": {
    "index_base": 0,
    "capacity": 2,
    "state_representation": "top为已存元素数",
    "not_applicable_reasons": []
  },
  "shared_example": {
    "input_description": "入栈6、9",
    "initial_state": "top=0",
    "steps": [
      {
        "operation": "执行固定示例",
        "expected_state": "top为1、2、1",
        "expected_output": "无打印，返回9"
      }
    ]
  },
  "prerequisite_node_ids": [],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "objective_ids": [
        "local"
      ],
      "depends_on": []
    },
    {
      "role": "code",
      "scene_key": "code",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation"
      ]
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation",
        "code"
      ]
    }
  ],
  "node_id": "stack",
  "graph_version": "mvp-0.2.0",
  "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
  "profile_version": null,
  "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
  "goal": "用C展示容量2的栈依次入栈6、9和一次出栈，明确追踪top和返回值，并用题目检查操作过程。",
  "code_language": "C",
  "schema_version": "learning-plan-v1",
  "references": [
    {
      "reference_id": "graph-node:mvp-0.2.0:stack",
      "version": "mvp-0.2.0",
      "digest": "fcd31b8e716614bb18a06dcac7e20afbfb1fa4dccccc1871a6391bc96ce121b0"
    }
  ]
}
```

### 学生可见 explanation

```json
{
  "markdown": "定长栈只做这两次入栈、一次出栈，不是可任意调用的通用接口。top从0到1到2，出栈先减到1，取a[1]=9，返回6，无打印；这组有限操作始终在容量2内。"
}
```

### 学生可见 code

```json
{
  "language": "C",
  "source": "int top_value(void) {\n    int a[2] = {6, 9};\n    int top = 0;\n    a[top++] = 6;\n    a[top++] = 9;\n    return a[--top];\n}",
  "expected_output": "无标准输出；由调用方获取返回值。",
  "key_steps": [
    "top表示元素数，也是下一写入位置；先减后取符合后进先出。"
  ],
  "display_only": true
}
```

### 学生可见 exercise

```json
{
  "items": [
    {
      "id": "q1",
      "question": "[判断题] 第二次入栈后top=2 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "两次递增得到2。"
    },
    {
      "id": "q2",
      "question": "[判断题] 出栈先令top=1再取a[1] 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "前置递减先执行。"
    },
    {
      "id": "q3",
      "question": "[判断题] 此次出栈返回最早放入的6 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "F",
      "explanation": "返回后放入的9。"
    }
  ]
}
```

### 动作/媒体

```json
{
  "version": "teaching-actions-v1",
  "actions": [
    {
      "kind": "show_resource",
      "scene_key": "explanation",
      "resource_id": "1af74274-0656-565d-9539-6106ab717be1",
      "resource_digest": "89c1966ab8924f97fa00a0bf0f12f7f3a9da88668a94fa7d1e9fe7846bd1f58b"
    },
    {
      "kind": "show_resource",
      "scene_key": "code",
      "resource_id": "026f5368-6144-5c32-9790-714c7db22af3",
      "resource_digest": "d2773e879760ea0e7c2ce77242908e7b85bdb4ad0a68c0df2856386d5299f02c"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "026f5368-6144-5c32-9790-714c7db22af3",
      "resource_digest": "d2773e879760ea0e7c2ce77242908e7b85bdb4ad0a68c0df2856386d5299f02c",
      "anchor_id": "a3"
    },
    {
      "kind": "show_resource",
      "scene_key": "exercise",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "exercise_id": "q1"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "exercise_id": "q2"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "exercise_id": "q3"
    }
  ],
  "anchor_catalog": [
    {
      "anchor_id": "a1",
      "resource_id": "1af74274-0656-565d-9539-6106ab717be1",
      "resource_digest": "89c1966ab8924f97fa00a0bf0f12f7f3a9da88668a94fa7d1e9fe7846bd1f58b",
      "json_pointer": "/markdown",
      "start_utf8": 0,
      "end_utf8": 198
    },
    {
      "anchor_id": "a2",
      "resource_id": "026f5368-6144-5c32-9790-714c7db22af3",
      "resource_digest": "d2773e879760ea0e7c2ce77242908e7b85bdb4ad0a68c0df2856386d5299f02c",
      "json_pointer": "/expected_output",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a3",
      "resource_id": "026f5368-6144-5c32-9790-714c7db22af3",
      "resource_digest": "d2773e879760ea0e7c2ce77242908e7b85bdb4ad0a68c0df2856386d5299f02c",
      "json_pointer": "/key_steps/0",
      "start_utf8": 0,
      "end_utf8": 81
    },
    {
      "anchor_id": "a4",
      "resource_id": "026f5368-6144-5c32-9790-714c7db22af3",
      "resource_digest": "d2773e879760ea0e7c2ce77242908e7b85bdb4ad0a68c0df2856386d5299f02c",
      "json_pointer": "/language",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a5",
      "resource_id": "026f5368-6144-5c32-9790-714c7db22af3",
      "resource_digest": "d2773e879760ea0e7c2ce77242908e7b85bdb4ad0a68c0df2856386d5299f02c",
      "json_pointer": "/source",
      "start_utf8": 0,
      "end_utf8": 120
    },
    {
      "anchor_id": "a6",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/0/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a7",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/0/explanation",
      "start_utf8": 0,
      "end_utf8": 22
    },
    {
      "anchor_id": "a8",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/0/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a9",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/0/question",
      "start_utf8": 0,
      "end_utf8": 78
    },
    {
      "anchor_id": "a10",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/1/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a11",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/1/explanation",
      "start_utf8": 0,
      "end_utf8": 24
    },
    {
      "anchor_id": "a12",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/1/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a13",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/1/question",
      "start_utf8": 0,
      "end_utf8": 82
    },
    {
      "anchor_id": "a14",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/2/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a15",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/2/explanation",
      "start_utf8": 0,
      "end_utf8": 22
    },
    {
      "anchor_id": "a16",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/2/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a17",
      "resource_id": "a56bc5d3-9da8-56a3-9847-b743fa5fbb3b",
      "resource_digest": "0246aaa2cf500e82c32357c5e8ea5174ba4f22eb08fdf115458ea26632a9d486",
      "json_pointer": "/items/2/question",
      "start_utf8": 0,
      "end_utf8": 89
    }
  ],
  "digest": "b86aec9b517cdd8d2b01f9dcdc3fe92514769e18465d7e9f90fc7a5a9d525a11"
}
```

本单元未承诺动画，动作不当成已播放动画。

### 标签理由/核对要求

- 指出返回值声明与实际程序矛盾，引用声明和程序；不得编造其他缺陷。

- 核对所有实际陈述与引用，不只检查主错误；任何附带不实意见不通过。

## holdout-stack-safety

预期：`reject`；独立签核：pending。

原始目标：用C展示容量2的栈依次入栈6、9和一次出栈，明确追踪top和返回值，并用题目检查操作过程。

本节授权目标：用C展示容量2的栈依次入栈6、9和一次出栈，明确追踪top和返回值，并用题目检查操作过程。

教学选择：target；目标/建议/教学节点：stack / stack / stack

完整计划（内部上下文，不算学生交付）：

```json
{
  "objectives": [
    {
      "id": "local",
      "text": "用C展示容量2的栈依次入栈6、9和一次出栈，明确追踪top和返回值，并用题目检查操作过程。"
    }
  ],
  "terminology": [
    {
      "term": "返回值",
      "meaning": "函数交给调用方的值，不等于打印"
    }
  ],
  "conventions": {
    "index_base": 0,
    "capacity": 2,
    "state_representation": "top为已存元素数",
    "not_applicable_reasons": []
  },
  "shared_example": {
    "input_description": "入栈6、9",
    "initial_state": "top=0",
    "steps": [
      {
        "operation": "执行固定示例",
        "expected_state": "top为1、2、1",
        "expected_output": "无打印，返回9"
      }
    ]
  },
  "prerequisite_node_ids": [],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "objective_ids": [
        "local"
      ],
      "depends_on": []
    },
    {
      "role": "code",
      "scene_key": "code",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation"
      ]
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation",
        "code"
      ]
    }
  ],
  "node_id": "stack",
  "graph_version": "mvp-0.2.0",
  "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
  "profile_version": null,
  "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
  "goal": "用C展示容量2的栈依次入栈6、9和一次出栈，明确追踪top和返回值，并用题目检查操作过程。",
  "code_language": "C",
  "schema_version": "learning-plan-v1",
  "references": [
    {
      "reference_id": "graph-node:mvp-0.2.0:stack",
      "version": "mvp-0.2.0",
      "digest": "fcd31b8e716614bb18a06dcac7e20afbfb1fa4dccccc1871a6391bc96ce121b0"
    }
  ]
}
```

### 学生可见 explanation

```json
{
  "markdown": "仅执行给定两次入栈和一次读取。top由0到1到2；读取a[top]。"
}
```

### 学生可见 code

```json
{
  "language": "C",
  "source": "int top_value(void) {\n    int a[2] = {6, 9};\n    int top = 0;\n    a[top++] = 6;\n    a[top++] = 9;\n    return a[top];\n}",
  "expected_output": "无标准输出；由调用方获取返回值。",
  "key_steps": [
    "top表示已存元素数；代码本次直接读取a[top]。"
  ],
  "display_only": true
}
```

### 学生可见 exercise

```json
{
  "items": [
    {
      "id": "q1",
      "question": "[判断题] 两次入栈后top=2 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "两个后置递增使top由0到2。"
    },
    {
      "id": "q2",
      "question": "[判断题] 长度2的数组允许读取a[2] 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "F",
      "explanation": "合法下标只有0和1。"
    },
    {
      "id": "q3",
      "question": "[判断题] 代码包含打印语句 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "F",
      "explanation": "没有打印语句。"
    }
  ]
}
```

### 动作/媒体

```json
{
  "version": "teaching-actions-v1",
  "actions": [
    {
      "kind": "show_resource",
      "scene_key": "explanation",
      "resource_id": "f0a8076b-0156-5dbd-881a-cc00c2fcef98",
      "resource_digest": "781419554c657ffce7c17cd29f289b5baddda3690177eb445c43293eb2703f91"
    },
    {
      "kind": "show_resource",
      "scene_key": "code",
      "resource_id": "8f7eb857-d531-52d7-b192-a28114c0e1b4",
      "resource_digest": "e923124e51de106163857c7ad4779ff25ac254dcdb202c20b51e351773680f54"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "8f7eb857-d531-52d7-b192-a28114c0e1b4",
      "resource_digest": "e923124e51de106163857c7ad4779ff25ac254dcdb202c20b51e351773680f54",
      "anchor_id": "a3"
    },
    {
      "kind": "show_resource",
      "scene_key": "exercise",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f",
      "exercise_id": "q1"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f",
      "exercise_id": "q2"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f",
      "exercise_id": "q3"
    }
  ],
  "anchor_catalog": [
    {
      "anchor_id": "a1",
      "resource_id": "f0a8076b-0156-5dbd-881a-cc00c2fcef98",
      "resource_digest": "781419554c657ffce7c17cd29f289b5baddda3690177eb445c43293eb2703f91",
      "json_pointer": "/markdown",
      "start_utf8": 0,
      "end_utf8": 78
    },
    {
      "anchor_id": "a2",
      "resource_id": "8f7eb857-d531-52d7-b192-a28114c0e1b4",
      "resource_digest": "e923124e51de106163857c7ad4779ff25ac254dcdb202c20b51e351773680f54",
      "json_pointer": "/expected_output",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a3",
      "resource_id": "8f7eb857-d531-52d7-b192-a28114c0e1b4",
      "resource_digest": "e923124e51de106163857c7ad4779ff25ac254dcdb202c20b51e351773680f54",
      "json_pointer": "/key_steps/0",
      "start_utf8": 0,
      "end_utf8": 60
    },
    {
      "anchor_id": "a4",
      "resource_id": "8f7eb857-d531-52d7-b192-a28114c0e1b4",
      "resource_digest": "e923124e51de106163857c7ad4779ff25ac254dcdb202c20b51e351773680f54",
      "json_pointer": "/language",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a5",
      "resource_id": "8f7eb857-d531-52d7-b192-a28114c0e1b4",
      "resource_digest": "e923124e51de106163857c7ad4779ff25ac254dcdb202c20b51e351773680f54",
      "json_pointer": "/source",
      "start_utf8": 0,
      "end_utf8": 118
    },
    {
      "anchor_id": "a6",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f",
      "json_pointer": "/items/0/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a7",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f",
      "json_pointer": "/items/0/explanation",
      "start_utf8": 0,
      "end_utf8": 35
    },
    {
      "anchor_id": "a8",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f",
      "json_pointer": "/items/0/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a9",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f",
      "json_pointer": "/items/0/question",
      "start_utf8": 0,
      "end_utf8": 75
    },
    {
      "anchor_id": "a10",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f",
      "json_pointer": "/items/1/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a11",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f",
      "json_pointer": "/items/1/explanation",
      "start_utf8": 0,
      "end_utf8": 26
    },
    {
      "anchor_id": "a12",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f",
      "json_pointer": "/items/1/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a13",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f",
      "json_pointer": "/items/1/question",
      "start_utf8": 0,
      "end_utf8": 87
    },
    {
      "anchor_id": "a14",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f",
      "json_pointer": "/items/2/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a15",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f",
      "json_pointer": "/items/2/explanation",
      "start_utf8": 0,
      "end_utf8": 21
    },
    {
      "anchor_id": "a16",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f",
      "json_pointer": "/items/2/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a17",
      "resource_id": "21f59166-3b7b-5003-a6e3-7724ca7983f5",
      "resource_digest": "e06f02db368c0c12f315093d3ab631ab3a4ec035bb314484dc4bf52f50da1f5f",
      "json_pointer": "/items/2/question",
      "start_utf8": 0,
      "end_utf8": 79
    }
  ],
  "digest": "bfd0e5a1b91aae9c68eb0018d681b85fb418f1d14ea1ec562a75d032ffc4735c"
}
```

本单元未承诺动画，动作不当成已播放动画。

### 标签理由/核对要求

- 指出实际可达越界及精确长度/索引；不得从未定义行为推出必然不等于某个数值。

- 本例未递减top，也未完成所承诺的出栈/返回值教学；该真实目标缺口须保留具体说明，不计附带误报。

- 核对所有实际陈述与引用，不只检查主错误；任何附带不实意见不通过。

## holdout-prerequisite

预期：`pass`；独立签核：pending。

原始目标：用C学习单链表头插法。

本节授权目标：为学习链表插入，本节先学习路径推荐的C 指针。原目标尚待后续完成。

教学选择：recommended；目标/建议/教学节点：linked-list-insertion / c-pointer / c-pointer

完整计划（内部上下文，不算学生交付）：

```json
{
  "objectives": [
    {
      "id": "local",
      "text": "为学习链表插入，本节先学习路径推荐的C 指针。原目标尚待后续完成。"
    }
  ],
  "terminology": [
    {
      "term": "返回值",
      "meaning": "函数交给调用方的值，不等于打印"
    }
  ],
  "conventions": {
    "index_base": null,
    "capacity": null,
    "state_representation": "p存value地址",
    "not_applicable_reasons": [
      "标量指针取值示例不涉及容器容量或下标。"
    ]
  },
  "shared_example": {
    "input_description": "value=12",
    "initial_state": "value初始化12",
    "steps": [
      {
        "operation": "执行固定示例",
        "expected_state": "p=&value，*p=12",
        "expected_output": "无打印，返回12"
      }
    ]
  },
  "prerequisite_node_ids": [],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "objective_ids": [
        "local"
      ],
      "depends_on": []
    },
    {
      "role": "code",
      "scene_key": "code",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation"
      ]
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "objective_ids": [
        "local"
      ],
      "depends_on": [
        "explanation",
        "code"
      ]
    }
  ],
  "node_id": "c-pointer",
  "graph_version": "mvp-0.2.0",
  "graph_digest": "3639db6aedc9699348e63b5e7e1bdaaea3189592b19540c64e8f175aceb9ef59",
  "profile_version": null,
  "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
  "goal": "为学习链表插入，本节先学习路径推荐的C 指针。原目标尚待后续完成。",
  "code_language": "C",
  "schema_version": "learning-plan-v1",
  "references": [
    {
      "reference_id": "graph-node:mvp-0.2.0:c-pointer",
      "version": "mvp-0.2.0",
      "digest": "038e80d56854aedbfc8a65e828b514eb532ebfea54abf7b933ebfe79f8b0dfdc"
    }
  ]
}
```

### 学生可见 explanation

```json
{
  "markdown": "本节只补C指针先修：p存value地址，*p读取12，返回12，不打印。本节尚未实现链表头插法，原目标留待后续。"
}
```

### 学生可见 code

```json
{
  "language": "C",
  "source": "int pointer_value(void) {\n    int value = 12;\n    int *p = &value;\n    return *p;\n}",
  "expected_output": "无标准输出；由调用方获取返回值。",
  "key_steps": [
    "取地址后解引用；p始终指向仍存活的局部value，读取发生在返回之前。"
  ],
  "display_only": true
}
```

### 学生可见 exercise

```json
{
  "items": [
    {
      "id": "q1",
      "question": "[判断题] p保存value的地址 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "&value取地址。"
    },
    {
      "id": "q2",
      "question": "[判断题] *p在本次读取为12 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "T",
      "explanation": "value已初始化为12。"
    },
    {
      "id": "q3",
      "question": "[判断题] 这一小节已经交付完整链表头插程序 仅填 T 或 F（T=正确，F=错误）。",
      "answer": "F",
      "explanation": "当前仅是授权的指针先修小节。"
    }
  ]
}
```

### 动作/媒体

```json
{
  "version": "teaching-actions-v1",
  "actions": [
    {
      "kind": "show_resource",
      "scene_key": "explanation",
      "resource_id": "9cc1c116-5d99-5ea8-84d7-290945d2a3d4",
      "resource_digest": "faa87ed2040132ee5f4895afdaae03c0e5e1e630446355c8373bbb493becced6"
    },
    {
      "kind": "show_resource",
      "scene_key": "code",
      "resource_id": "15aff961-0d46-5f88-a538-c0a4e8df42d3",
      "resource_digest": "e9565e5fa99a977a86c65e520a58d159a6d3e815d38ca27dd2f6c0595280a1cc"
    },
    {
      "kind": "highlight",
      "scene_key": "code",
      "resource_id": "15aff961-0d46-5f88-a538-c0a4e8df42d3",
      "resource_digest": "e9565e5fa99a977a86c65e520a58d159a6d3e815d38ca27dd2f6c0595280a1cc",
      "anchor_id": "a3"
    },
    {
      "kind": "show_resource",
      "scene_key": "exercise",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96",
      "exercise_id": "q1"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96",
      "exercise_id": "q2"
    },
    {
      "kind": "ask_exercise",
      "scene_key": "exercise",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96",
      "exercise_id": "q3"
    }
  ],
  "anchor_catalog": [
    {
      "anchor_id": "a1",
      "resource_id": "9cc1c116-5d99-5ea8-84d7-290945d2a3d4",
      "resource_digest": "faa87ed2040132ee5f4895afdaae03c0e5e1e630446355c8373bbb493becced6",
      "json_pointer": "/markdown",
      "start_utf8": 0,
      "end_utf8": 142
    },
    {
      "anchor_id": "a2",
      "resource_id": "15aff961-0d46-5f88-a538-c0a4e8df42d3",
      "resource_digest": "e9565e5fa99a977a86c65e520a58d159a6d3e815d38ca27dd2f6c0595280a1cc",
      "json_pointer": "/expected_output",
      "start_utf8": 0,
      "end_utf8": 48
    },
    {
      "anchor_id": "a3",
      "resource_id": "15aff961-0d46-5f88-a538-c0a4e8df42d3",
      "resource_digest": "e9565e5fa99a977a86c65e520a58d159a6d3e815d38ca27dd2f6c0595280a1cc",
      "json_pointer": "/key_steps/0",
      "start_utf8": 0,
      "end_utf8": 93
    },
    {
      "anchor_id": "a4",
      "resource_id": "15aff961-0d46-5f88-a538-c0a4e8df42d3",
      "resource_digest": "e9565e5fa99a977a86c65e520a58d159a6d3e815d38ca27dd2f6c0595280a1cc",
      "json_pointer": "/language",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a5",
      "resource_id": "15aff961-0d46-5f88-a538-c0a4e8df42d3",
      "resource_digest": "e9565e5fa99a977a86c65e520a58d159a6d3e815d38ca27dd2f6c0595280a1cc",
      "json_pointer": "/source",
      "start_utf8": 0,
      "end_utf8": 83
    },
    {
      "anchor_id": "a6",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96",
      "json_pointer": "/items/0/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a7",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96",
      "json_pointer": "/items/0/explanation",
      "start_utf8": 0,
      "end_utf8": 18
    },
    {
      "anchor_id": "a8",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96",
      "json_pointer": "/items/0/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a9",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96",
      "json_pointer": "/items/0/question",
      "start_utf8": 0,
      "end_utf8": 76
    },
    {
      "anchor_id": "a10",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96",
      "json_pointer": "/items/1/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a11",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96",
      "json_pointer": "/items/1/explanation",
      "start_utf8": 0,
      "end_utf8": 25
    },
    {
      "anchor_id": "a12",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96",
      "json_pointer": "/items/1/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a13",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96",
      "json_pointer": "/items/1/question",
      "start_utf8": 0,
      "end_utf8": 77
    },
    {
      "anchor_id": "a14",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96",
      "json_pointer": "/items/2/answer",
      "start_utf8": 0,
      "end_utf8": 1
    },
    {
      "anchor_id": "a15",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96",
      "json_pointer": "/items/2/explanation",
      "start_utf8": 0,
      "end_utf8": 42
    },
    {
      "anchor_id": "a16",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96",
      "json_pointer": "/items/2/id",
      "start_utf8": 0,
      "end_utf8": 2
    },
    {
      "anchor_id": "a17",
      "resource_id": "6353bd32-5272-5e80-974a-de3670f04d18",
      "resource_digest": "699500d0aaef39db6ba3915049b11e4a3ddefa8ee63925305c00b614eb83aa96",
      "json_pointer": "/items/2/question",
      "start_utf8": 0,
      "end_utf8": 103
    }
  ],
  "digest": "1c3a468d1cf7d0c807e5dc2a40f93d335a58164f0bf8aa394e09dbfa558bc747"
}
```

本单元未承诺动画，动作不当成已播放动画。

### 标签理由/核对要求

- 所有必检ID齐全，findings/unchecked/unresolved均为空；无附带误报。

- 核对所有实际陈述与引用，不只检查主错误；任何附带不实意见不通过。
