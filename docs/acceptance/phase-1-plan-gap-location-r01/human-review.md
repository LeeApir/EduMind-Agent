# plan-only-gap单次定位：材料与判据

未绑定本包真实预算/标签批准。最多一次，成功或失败后停止。
预期needs_human，具体说明学生可见循环状态与退出边界支持不足；内部计划不算交付；不得虚构缺调用示例fact。
目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
材料摘要：c19deec758d9756b548b797f9af13dcff587143d523c1a25be76d9dd96e74ab3
```json
{
  "binding": {
    "owner_id": "136b4346-729d-5cb6-b21f-8b6ff797f38c",
    "unit_id": "27ec99ce-af58-506b-b3bd-1260f1d9b8f8",
    "operation_id": "c911820d-1467-5bca-b0b7-a72733d1a929",
    "plan_id": "4837ed48-16bb-5017-94ac-b380d0074462",
    "plan_version": 1,
    "plan_digest": "6e001c28456d4841817de40632d24d87c231159d61bf15f53d4c9ae57d07d8f1",
    "input_digest": "ef8f69cb35a786584eff9a40380be6cdae7e454f792b3424d78c99627083c4d9",
    "references_digest": "73c808e61d8d171633df56ec547afd4c0172facc4598782432d22880d9c8841c",
    "policy_version": "hybrid-review-v1",
    "policy_digest": "0ae5cb21ae5713f8f25491c3e09596a2519e1f8f45a656bd05dd4ecaed51320e"
  },
  "plan": {
    "objectives": [
      {
        "id": "sum",
        "text": "逐步追踪total=2、7、16及i=3时不再访问数组的边界"
      }
    ],
    "terminology": [
      {
        "term": "i",
        "meaning": "从0开始的数组下标"
      }
    ],
    "conventions": {
      "index_base": 0,
      "capacity": 3,
      "state_representation": "a={2,5,9}; total表示已处理元素之和",
      "not_applicable_reasons": []
    },
    "shared_example": {
      "input_description": "a={2,5,9}",
      "initial_state": "total=0",
      "steps": [
        {
          "operation": "i=0,1,2累加a[i]",
          "expected_state": "total依次2,7,16",
          "expected_output": null
        },
        {
          "operation": "i=3检查i<3",
          "expected_state": "条件为假，退出且不访问a[3]",
          "expected_output": "16"
        }
      ]
    },
    "prerequisite_node_ids": [],
    "scenes": [
      {
        "role": "explanation",
        "scene_key": "explanation",
        "objective_ids": [
          "sum"
        ],
        "depends_on": []
      },
      {
        "role": "code",
        "scene_key": "code",
        "objective_ids": [
          "sum"
        ],
        "depends_on": [
          "explanation"
        ]
      },
      {
        "role": "exercise",
        "scene_key": "exercise",
        "objective_ids": [
          "sum"
        ],
        "depends_on": [
          "explanation",
          "code"
        ]
      }
    ],
    "node_id": "array",
    "graph_version": "phase-1.1.0",
    "graph_digest": "2caffdbb1f523de8acbb412d2a4a231a49f7ce08da86ba45811f2f41b60c021a",
    "profile_version": null,
    "profile_evidence_digest": "8838fdd11ee58e08fd54a21272313e784012370b7cf0a2cde8b823ed8806d85d",
    "goal": "用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。",
    "code_language": "C",
    "schema_version": "learning-plan-v1",
    "references": [
      {
        "reference_id": "graph-node:phase-1.1.0:array",
        "version": "phase-1.1.0",
        "digest": "f83fd12e754fcda4124aa62b8a29203d97a897605d23dc4e37877393dcb0015d"
      }
    ]
  },
  "candidates": [
    {
      "resource_id": "da5782b3-1bbf-586f-92e2-2b406985b6dd",
      "role": "explanation",
      "envelope": {
        "resource_type": "explanation",
        "prompt_version": "learning-resources-v1",
        "content": {
          "markdown": "a={2,5,9}，容量3，下标0、1、2。sum()返回16，不直接打印。"
        }
      },
      "content_digest": "2d21823e29bd9139d109a5436b13ef37487914c57636405a88be2e1b53d7d942",
      "dependency_digest": "128c8ec3392e9565051dfdd1da5aaac1cd75c300d3415189cb98cd93a304ddef",
      "upstream": []
    },
    {
      "resource_id": "e7900988-fc3c-54e8-ae25-e54e73a85eae",
      "role": "code",
      "envelope": {
        "resource_type": "code",
        "prompt_version": "learning-resources-v1",
        "content": {
          "language": "C",
          "source": "#include <stddef.h>\nint sum(void){int a[3]={2,5,9};int total=0;for(int i=0;i<3;i++)total+=a[i];return total;}",
          "expected_output": "不打印；由调用方取得返回值。",
          "key_steps": [
            "遍历并求和后返回结果。"
          ],
          "display_only": true
        }
      },
      "content_digest": "371024bcb52809cfa8ed99cde3780ef8c1e364d5c84e98628169873ca5007e59",
      "dependency_digest": "575070645a2c9274472d92954ea0ba45b393a401d0529e75f813c8df15150e7e",
      "upstream": [
        {
          "resource_id": "da5782b3-1bbf-586f-92e2-2b406985b6dd",
          "content_digest": "2d21823e29bd9139d109a5436b13ef37487914c57636405a88be2e1b53d7d942",
          "dependency_digest": "128c8ec3392e9565051dfdd1da5aaac1cd75c300d3415189cb98cd93a304ddef"
        }
      ]
    },
    {
      "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
      "role": "exercise",
      "envelope": {
        "resource_type": "exercise",
        "prompt_version": "learning-resources-v1",
        "content": {
          "items": [
            {
              "id": "q1",
              "question": "[判断题] 长度为3的数组合法下标为0、1、2。仅填 T 或 F（T=正确，F=错误）",
              "answer": "T",
              "explanation": "从0开始，最后下标为长度减1。"
            },
            {
              "id": "q2",
              "question": "[判断题] 2+5+9=16。仅填 T 或 F（T=正确，F=错误）",
              "answer": "T",
              "explanation": "2+5=7，7+9=16。"
            },
            {
              "id": "q3",
              "question": "[判断题] 返回值必然直接打印到屏幕。仅填 T 或 F（T=正确，F=错误）",
              "answer": "F",
              "explanation": "返回值传给调用方；本例没有打印语句。"
            }
          ]
        }
      },
      "content_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
      "dependency_digest": "c917a78c41b2f8ff1f4b7603ef72812d8835f013fff9be360108f7f81141e760",
      "upstream": [
        {
          "resource_id": "da5782b3-1bbf-586f-92e2-2b406985b6dd",
          "content_digest": "2d21823e29bd9139d109a5436b13ef37487914c57636405a88be2e1b53d7d942",
          "dependency_digest": "128c8ec3392e9565051dfdd1da5aaac1cd75c300d3415189cb98cd93a304ddef"
        },
        {
          "resource_id": "e7900988-fc3c-54e8-ae25-e54e73a85eae",
          "content_digest": "371024bcb52809cfa8ed99cde3780ef8c1e364d5c84e98628169873ca5007e59",
          "dependency_digest": "575070645a2c9274472d92954ea0ba45b393a401d0529e75f813c8df15150e7e"
        }
      ]
    }
  ],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "scene_id": "a6f4ede8-9536-530f-9b08-19fb3685573d",
      "scene_version": 1,
      "resource_id": "da5782b3-1bbf-586f-92e2-2b406985b6dd",
      "resource_digest": "2d21823e29bd9139d109a5436b13ef37487914c57636405a88be2e1b53d7d942",
      "dependency_digest": "128c8ec3392e9565051dfdd1da5aaac1cd75c300d3415189cb98cd93a304ddef"
    },
    {
      "role": "code",
      "scene_key": "code",
      "scene_id": "4f7f1411-4290-5c56-92ed-9249c322193c",
      "scene_version": 1,
      "resource_id": "e7900988-fc3c-54e8-ae25-e54e73a85eae",
      "resource_digest": "371024bcb52809cfa8ed99cde3780ef8c1e364d5c84e98628169873ca5007e59",
      "dependency_digest": "575070645a2c9274472d92954ea0ba45b393a401d0529e75f813c8df15150e7e"
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "scene_id": "78b46ace-5baf-54d7-9bd0-ee5206c32ac3",
      "scene_version": 1,
      "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
      "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
      "dependency_digest": "c917a78c41b2f8ff1f4b7603ef72812d8835f013fff9be360108f7f81141e760"
    }
  ],
  "actions": {
    "version": "teaching-actions-v1",
    "actions": [
      {
        "kind": "show_resource",
        "scene_key": "explanation",
        "resource_id": "da5782b3-1bbf-586f-92e2-2b406985b6dd",
        "resource_digest": "2d21823e29bd9139d109a5436b13ef37487914c57636405a88be2e1b53d7d942"
      },
      {
        "kind": "show_resource",
        "scene_key": "code",
        "resource_id": "e7900988-fc3c-54e8-ae25-e54e73a85eae",
        "resource_digest": "371024bcb52809cfa8ed99cde3780ef8c1e364d5c84e98628169873ca5007e59"
      },
      {
        "kind": "highlight",
        "scene_key": "code",
        "resource_id": "e7900988-fc3c-54e8-ae25-e54e73a85eae",
        "resource_digest": "371024bcb52809cfa8ed99cde3780ef8c1e364d5c84e98628169873ca5007e59",
        "anchor_id": "a3"
      },
      {
        "kind": "show_resource",
        "scene_key": "exercise",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "exercise_id": "q1"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "exercise_id": "q2"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "exercise_id": "q3"
      }
    ],
    "anchor_catalog": [
      {
        "anchor_id": "a1",
        "resource_id": "da5782b3-1bbf-586f-92e2-2b406985b6dd",
        "resource_digest": "2d21823e29bd9139d109a5436b13ef37487914c57636405a88be2e1b53d7d942",
        "json_pointer": "/markdown",
        "start_utf8": 0,
        "end_utf8": 74
      },
      {
        "anchor_id": "a2",
        "resource_id": "e7900988-fc3c-54e8-ae25-e54e73a85eae",
        "resource_digest": "371024bcb52809cfa8ed99cde3780ef8c1e364d5c84e98628169873ca5007e59",
        "json_pointer": "/expected_output",
        "start_utf8": 0,
        "end_utf8": 42
      },
      {
        "anchor_id": "a3",
        "resource_id": "e7900988-fc3c-54e8-ae25-e54e73a85eae",
        "resource_digest": "371024bcb52809cfa8ed99cde3780ef8c1e364d5c84e98628169873ca5007e59",
        "json_pointer": "/key_steps/0",
        "start_utf8": 0,
        "end_utf8": 33
      },
      {
        "anchor_id": "a4",
        "resource_id": "e7900988-fc3c-54e8-ae25-e54e73a85eae",
        "resource_digest": "371024bcb52809cfa8ed99cde3780ef8c1e364d5c84e98628169873ca5007e59",
        "json_pointer": "/language",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a5",
        "resource_id": "e7900988-fc3c-54e8-ae25-e54e73a85eae",
        "resource_digest": "371024bcb52809cfa8ed99cde3780ef8c1e364d5c84e98628169873ca5007e59",
        "json_pointer": "/source",
        "start_utf8": 0,
        "end_utf8": 109
      },
      {
        "anchor_id": "a6",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/0/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a7",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/0/explanation",
        "start_utf8": 0,
        "end_utf8": 41
      },
      {
        "anchor_id": "a8",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/0/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a9",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/0/question",
        "start_utf8": 0,
        "end_utf8": 97
      },
      {
        "anchor_id": "a10",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/1/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a11",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/1/explanation",
        "start_utf8": 0,
        "end_utf8": 17
      },
      {
        "anchor_id": "a12",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/1/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a13",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/1/question",
        "start_utf8": 0,
        "end_utf8": 62
      },
      {
        "anchor_id": "a14",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/2/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a15",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/2/explanation",
        "start_utf8": 0,
        "end_utf8": 54
      },
      {
        "anchor_id": "a16",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/2/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a17",
        "resource_id": "a9c6f160-c0b8-5c80-adcb-fca063308dc3",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/2/question",
        "start_utf8": 0,
        "end_utf8": 90
      }
    ],
    "digest": "52fbc2dc7474344d5f6163e8782bd86a6aae5e5ec42fee92b3a51ee9010037c6"
  },
  "reference_context": {
    "source": {
      "reference_id": "graph-node:phase-1.1.0:array",
      "version": "phase-1.1.0",
      "digest": "f83fd12e754fcda4124aa62b8a29203d97a897605d23dc4e37877393dcb0015d"
    },
    "node": {
      "id": "array",
      "name": "数组",
      "chapter": "线性表",
      "difficulty": 1,
      "description": "使用连续存储空间、通过下标访问元素的线性结构。",
      "prerequisites": [],
      "learning_objectives": [
        "说出下标访问的时间复杂度",
        "说明连续存储对插入和删除的影响"
      ],
      "common_misconceptions": [
        "数组每次访问都要从头遍历",
        "数组插入总是 O(1)"
      ],
      "ai_context": "使用连续格子和下标精灵的图示，对比中间插入时的元素搬移。",
      "mastery_rule_key": "linear-structure-v1"
    },
    "learner_evidence": {},
    "scope": "Partial graph; proposed trace is not independently verified evidence."
  },
  "unit_digest": "8eec1ba97cdee9ecbc8bdf343335664d348c98d0bea6ae27f4b7f1e994edc31f"
}
```
