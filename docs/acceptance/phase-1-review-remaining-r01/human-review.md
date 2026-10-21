# 其余五类：实际材料与冻结判据

零调用提案，未绑定真实预算/标签批准，不预签模型结果。

## assessment-gap:candidate
needs_human; explicitly distinguish already taught states/exit from missing process assessment; no findings or invented facts.
原始目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。并用题目检验学生是否掌握循环过程。
材料摘要：530af5709da6a592e94bd3f5128892b76a66337a74a84d0a914f1cd1075d92e3
wire摘要：bbadd5aabb2ca38f96c54dbecf202c97ccf7025d285bb5188dda81c029e88559
```json
{
  "binding": {
    "owner_id": "350c2a14-17be-5f5a-9f44-19adbd62b2aa",
    "unit_id": "d8973d5b-ec0a-5b77-8106-a53bba6b77c8",
    "operation_id": "76f160ba-1035-5f7e-8213-05c12c77386d",
    "plan_id": "8defc88d-babf-5898-a06d-57fcfec7ab5f",
    "plan_version": 1,
    "plan_digest": "e87214f056034c2b9039a79c94c9df92e301b751a46cff0c7662b5b5c2130ec5",
    "input_digest": "8ef875aae05da2456766aa408bc2480eb889d2e97f39a119bd21936d356cbba5",
    "references_digest": "73c808e61d8d171633df56ec547afd4c0172facc4598782432d22880d9c8841c",
    "policy_version": "hybrid-review-v1",
    "policy_digest": "0ae5cb21ae5713f8f25491c3e09596a2519e1f8f45a656bd05dd4ecaed51320e"
  },
  "plan": {
    "objectives": [
      {
        "id": "sum",
        "text": "逐步追踪total=2、7、16及i=3时不再访问数组的边界，用题目检验中间状态和退出条件知识。"
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
    "goal": "用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。并用题目检验学生是否掌握循环过程。",
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
      "resource_id": "d4b0fac3-4986-537b-9a51-e0f605db753b",
      "role": "explanation",
      "envelope": {
        "resource_type": "explanation",
        "prompt_version": "learning-resources-v1",
        "content": {
          "markdown": "a={2,5,9}，容量3，下标0、1、2。total初始为0。i=0读取a[0]=2后total=2；i=1读取a[1]=5后total=7；i=2读取a[2]=9后total=16。i增至3，i<3为假，停止循环，不访问a[3]，循环体恰执行3次。sum()返回16，不直接打印。"
        }
      },
      "content_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
      "dependency_digest": "366bc4e0e4b25a9f9959e47c88f36f859f116a3249e975d17eee71bae78e4b05",
      "upstream": []
    },
    {
      "resource_id": "3016b23d-258c-5b5a-93bb-9a7ec53ecc7c",
      "role": "code",
      "envelope": {
        "resource_type": "code",
        "prompt_version": "learning-resources-v1",
        "content": {
          "language": "C",
          "source": "#include <stddef.h>\nint sum(void){int a[3]={2,5,9};int total=0;for(int i=0;i<3;i++)total+=a[i];return total;}",
          "expected_output": "不打印；由调用方取得返回值。",
          "key_steps": [
            "total从0开始依次变为2、7、16。",
            "i=3时i<3为假，停止且不访问a[3]。"
          ],
          "display_only": true
        }
      },
      "content_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
      "dependency_digest": "318013fa2e6cd08fa87b741c863f19262e9dbb9ba9168489ee0598d37986eb57",
      "upstream": [
        {
          "resource_id": "d4b0fac3-4986-537b-9a51-e0f605db753b",
          "content_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
          "dependency_digest": "366bc4e0e4b25a9f9959e47c88f36f859f116a3249e975d17eee71bae78e4b05"
        }
      ]
    },
    {
      "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
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
      "dependency_digest": "335321e512f15d44996ef5123fb7edc9155ac90b56fc046d3b0f1f0718d3fdbc",
      "upstream": [
        {
          "resource_id": "d4b0fac3-4986-537b-9a51-e0f605db753b",
          "content_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
          "dependency_digest": "366bc4e0e4b25a9f9959e47c88f36f859f116a3249e975d17eee71bae78e4b05"
        },
        {
          "resource_id": "3016b23d-258c-5b5a-93bb-9a7ec53ecc7c",
          "content_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
          "dependency_digest": "318013fa2e6cd08fa87b741c863f19262e9dbb9ba9168489ee0598d37986eb57"
        }
      ]
    }
  ],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "scene_id": "576bf2d4-8655-5c6a-abdd-7554662a3139",
      "scene_version": 1,
      "resource_id": "d4b0fac3-4986-537b-9a51-e0f605db753b",
      "resource_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
      "dependency_digest": "366bc4e0e4b25a9f9959e47c88f36f859f116a3249e975d17eee71bae78e4b05"
    },
    {
      "role": "code",
      "scene_key": "code",
      "scene_id": "61aa7462-c159-543e-8737-96b79f18a033",
      "scene_version": 1,
      "resource_id": "3016b23d-258c-5b5a-93bb-9a7ec53ecc7c",
      "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
      "dependency_digest": "318013fa2e6cd08fa87b741c863f19262e9dbb9ba9168489ee0598d37986eb57"
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "scene_id": "e1c90e39-ccfd-5db4-a0a9-2567f16412b7",
      "scene_version": 1,
      "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
      "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
      "dependency_digest": "335321e512f15d44996ef5123fb7edc9155ac90b56fc046d3b0f1f0718d3fdbc"
    }
  ],
  "actions": {
    "version": "teaching-actions-v1",
    "actions": [
      {
        "kind": "show_resource",
        "scene_key": "explanation",
        "resource_id": "d4b0fac3-4986-537b-9a51-e0f605db753b",
        "resource_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1"
      },
      {
        "kind": "show_resource",
        "scene_key": "code",
        "resource_id": "3016b23d-258c-5b5a-93bb-9a7ec53ecc7c",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60"
      },
      {
        "kind": "highlight",
        "scene_key": "code",
        "resource_id": "3016b23d-258c-5b5a-93bb-9a7ec53ecc7c",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "anchor_id": "a3"
      },
      {
        "kind": "highlight",
        "scene_key": "code",
        "resource_id": "3016b23d-258c-5b5a-93bb-9a7ec53ecc7c",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "anchor_id": "a4"
      },
      {
        "kind": "show_resource",
        "scene_key": "exercise",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "exercise_id": "q1"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "exercise_id": "q2"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "exercise_id": "q3"
      }
    ],
    "anchor_catalog": [
      {
        "anchor_id": "a1",
        "resource_id": "d4b0fac3-4986-537b-9a51-e0f605db753b",
        "resource_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
        "json_pointer": "/markdown",
        "start_utf8": 0,
        "end_utf8": 256
      },
      {
        "anchor_id": "a2",
        "resource_id": "3016b23d-258c-5b5a-93bb-9a7ec53ecc7c",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/expected_output",
        "start_utf8": 0,
        "end_utf8": 42
      },
      {
        "anchor_id": "a3",
        "resource_id": "3016b23d-258c-5b5a-93bb-9a7ec53ecc7c",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/key_steps/0",
        "start_utf8": 0,
        "end_utf8": 40
      },
      {
        "anchor_id": "a4",
        "resource_id": "3016b23d-258c-5b5a-93bb-9a7ec53ecc7c",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/key_steps/1",
        "start_utf8": 0,
        "end_utf8": 43
      },
      {
        "anchor_id": "a5",
        "resource_id": "3016b23d-258c-5b5a-93bb-9a7ec53ecc7c",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/language",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a6",
        "resource_id": "3016b23d-258c-5b5a-93bb-9a7ec53ecc7c",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/source",
        "start_utf8": 0,
        "end_utf8": 109
      },
      {
        "anchor_id": "a7",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/0/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a8",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/0/explanation",
        "start_utf8": 0,
        "end_utf8": 41
      },
      {
        "anchor_id": "a9",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/0/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a10",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/0/question",
        "start_utf8": 0,
        "end_utf8": 97
      },
      {
        "anchor_id": "a11",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/1/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a12",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/1/explanation",
        "start_utf8": 0,
        "end_utf8": 17
      },
      {
        "anchor_id": "a13",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/1/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a14",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/1/question",
        "start_utf8": 0,
        "end_utf8": 62
      },
      {
        "anchor_id": "a15",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/2/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a16",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/2/explanation",
        "start_utf8": 0,
        "end_utf8": 54
      },
      {
        "anchor_id": "a17",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/2/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a18",
        "resource_id": "e807ccd6-e8ac-55ea-a104-974e24e19a73",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/2/question",
        "start_utf8": 0,
        "end_utf8": 90
      }
    ],
    "digest": "7d847c4eed043f808257caa17141e02ce0b3885ebf7f25fd139ea540b04df7a0"
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
  "unit_digest": "8b0cf2030645d6a48d3fc5f42159a4c1cc9f16c4d78c8187753755c588ddfb78"
}
```

## fact-contradiction:candidate
reject; major/severe fact concretely identifies explanation return18 versus actual loop sum16.
原始目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
材料摘要：8bede9d8eb0c83a47c748a66af6eeaab4db474653c51e51d9de875c7e4717bd6
wire摘要：0aee3d1068a17a0045c872e850d053d50da7fd5c308628470eb9168f9f5ae3af
```json
{
  "binding": {
    "owner_id": "a375d2b3-8d44-5139-98e5-800d6276807d",
    "unit_id": "43268d18-fec9-547c-8cbf-6f7a49cf6fde",
    "operation_id": "94d6a762-80c2-51cc-b642-4027ff611a00",
    "plan_id": "e3276e2f-91b7-52a5-acf4-5c92bf133af8",
    "plan_version": 1,
    "plan_digest": "ccb45b98baf66a17044496e86e13d9cbca29e0bad35660c9dce3d90a55cca532",
    "input_digest": "e7bdf346a7566983dabf73640b176819a5f8b8018c02f1d11753de9ada0b7691",
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
          "operation": "遍历i=0,1,2并累加a[i]",
          "expected_state": "total依次为2,7,16",
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
      "resource_id": "fccaefd9-fcc8-56c4-8e67-4242f35be50d",
      "role": "explanation",
      "envelope": {
        "resource_type": "explanation",
        "prompt_version": "learning-resources-v1",
        "content": {
          "markdown": "a={2,5,9}，容量3，下标0、1、2。total初始为0。i=0读取a[0]=2后total=2；i=1读取a[1]=5后total=7；i=2读取a[2]=9后total=16。i增至3，i<3为假，停止循环，不访问a[3]，循环体恰执行3次。sum()返回18，不直接打印。"
        }
      },
      "content_digest": "aabfa9dbf8c9eb7914528cb1f94c7154432e47415d5e6e139b775fd513830450",
      "dependency_digest": "41edd66f73110a496e8d63eea4d429719b5481417cc398f3a0b9396ec01f4c59",
      "upstream": []
    },
    {
      "resource_id": "58bb0ed5-8527-5ae3-a882-d0884fcf4391",
      "role": "code",
      "envelope": {
        "resource_type": "code",
        "prompt_version": "learning-resources-v1",
        "content": {
          "language": "C",
          "source": "#include <stddef.h>\nint sum(void){int a[3]={2,5,9};int total=0;for(int i=0;i<3;i++)total+=a[i];return total;}",
          "expected_output": "不打印；由调用方取得返回值。",
          "key_steps": [
            "total从0开始依次变为2、7、16。",
            "i=3时i<3为假，停止且不访问a[3]。"
          ],
          "display_only": true
        }
      },
      "content_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
      "dependency_digest": "a79b503d652566af25e140140fd3b8b9f704d9c8f288edc415c787cd5af8f5e6",
      "upstream": [
        {
          "resource_id": "fccaefd9-fcc8-56c4-8e67-4242f35be50d",
          "content_digest": "aabfa9dbf8c9eb7914528cb1f94c7154432e47415d5e6e139b775fd513830450",
          "dependency_digest": "41edd66f73110a496e8d63eea4d429719b5481417cc398f3a0b9396ec01f4c59"
        }
      ]
    },
    {
      "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
      "role": "exercise",
      "envelope": {
        "resource_type": "exercise",
        "prompt_version": "learning-resources-v1",
        "content": {
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
      },
      "content_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
      "dependency_digest": "eaa8aff0c66305fb3ff560a87c8702dc5aede1ed00a0ab3f057ee5fb800648c4",
      "upstream": [
        {
          "resource_id": "fccaefd9-fcc8-56c4-8e67-4242f35be50d",
          "content_digest": "aabfa9dbf8c9eb7914528cb1f94c7154432e47415d5e6e139b775fd513830450",
          "dependency_digest": "41edd66f73110a496e8d63eea4d429719b5481417cc398f3a0b9396ec01f4c59"
        },
        {
          "resource_id": "58bb0ed5-8527-5ae3-a882-d0884fcf4391",
          "content_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
          "dependency_digest": "a79b503d652566af25e140140fd3b8b9f704d9c8f288edc415c787cd5af8f5e6"
        }
      ]
    }
  ],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "scene_id": "45e44def-97d9-5d02-8c37-019e1a3018f7",
      "scene_version": 1,
      "resource_id": "fccaefd9-fcc8-56c4-8e67-4242f35be50d",
      "resource_digest": "aabfa9dbf8c9eb7914528cb1f94c7154432e47415d5e6e139b775fd513830450",
      "dependency_digest": "41edd66f73110a496e8d63eea4d429719b5481417cc398f3a0b9396ec01f4c59"
    },
    {
      "role": "code",
      "scene_key": "code",
      "scene_id": "2a7de0f6-da6a-51c2-b059-7738a40adf73",
      "scene_version": 1,
      "resource_id": "58bb0ed5-8527-5ae3-a882-d0884fcf4391",
      "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
      "dependency_digest": "a79b503d652566af25e140140fd3b8b9f704d9c8f288edc415c787cd5af8f5e6"
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "scene_id": "5104e8f9-bf76-55ff-be3b-cf29a95a19d5",
      "scene_version": 1,
      "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
      "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
      "dependency_digest": "eaa8aff0c66305fb3ff560a87c8702dc5aede1ed00a0ab3f057ee5fb800648c4"
    }
  ],
  "actions": {
    "version": "teaching-actions-v1",
    "actions": [
      {
        "kind": "show_resource",
        "scene_key": "explanation",
        "resource_id": "fccaefd9-fcc8-56c4-8e67-4242f35be50d",
        "resource_digest": "aabfa9dbf8c9eb7914528cb1f94c7154432e47415d5e6e139b775fd513830450"
      },
      {
        "kind": "show_resource",
        "scene_key": "code",
        "resource_id": "58bb0ed5-8527-5ae3-a882-d0884fcf4391",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60"
      },
      {
        "kind": "highlight",
        "scene_key": "code",
        "resource_id": "58bb0ed5-8527-5ae3-a882-d0884fcf4391",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "anchor_id": "a3"
      },
      {
        "kind": "highlight",
        "scene_key": "code",
        "resource_id": "58bb0ed5-8527-5ae3-a882-d0884fcf4391",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "anchor_id": "a4"
      },
      {
        "kind": "show_resource",
        "scene_key": "exercise",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "exercise_id": "q1"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "exercise_id": "q2"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "exercise_id": "q3"
      }
    ],
    "anchor_catalog": [
      {
        "anchor_id": "a1",
        "resource_id": "fccaefd9-fcc8-56c4-8e67-4242f35be50d",
        "resource_digest": "aabfa9dbf8c9eb7914528cb1f94c7154432e47415d5e6e139b775fd513830450",
        "json_pointer": "/markdown",
        "start_utf8": 0,
        "end_utf8": 256
      },
      {
        "anchor_id": "a2",
        "resource_id": "58bb0ed5-8527-5ae3-a882-d0884fcf4391",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/expected_output",
        "start_utf8": 0,
        "end_utf8": 42
      },
      {
        "anchor_id": "a3",
        "resource_id": "58bb0ed5-8527-5ae3-a882-d0884fcf4391",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/key_steps/0",
        "start_utf8": 0,
        "end_utf8": 40
      },
      {
        "anchor_id": "a4",
        "resource_id": "58bb0ed5-8527-5ae3-a882-d0884fcf4391",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/key_steps/1",
        "start_utf8": 0,
        "end_utf8": 43
      },
      {
        "anchor_id": "a5",
        "resource_id": "58bb0ed5-8527-5ae3-a882-d0884fcf4391",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/language",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a6",
        "resource_id": "58bb0ed5-8527-5ae3-a882-d0884fcf4391",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/source",
        "start_utf8": 0,
        "end_utf8": 109
      },
      {
        "anchor_id": "a7",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a8",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/explanation",
        "start_utf8": 0,
        "end_utf8": 46
      },
      {
        "anchor_id": "a9",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a10",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/question",
        "start_utf8": 0,
        "end_utf8": 85
      },
      {
        "anchor_id": "a11",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a12",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/explanation",
        "start_utf8": 0,
        "end_utf8": 52
      },
      {
        "anchor_id": "a13",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a14",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/question",
        "start_utf8": 0,
        "end_utf8": 91
      },
      {
        "anchor_id": "a15",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a16",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/explanation",
        "start_utf8": 0,
        "end_utf8": 57
      },
      {
        "anchor_id": "a17",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a18",
        "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/question",
        "start_utf8": 0,
        "end_utf8": 88
      }
    ],
    "digest": "378fe42e3e8387ffd4a53ef25c33d1c308b994600349ede8a9e056a4fc7dd0dd"
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
  "unit_digest": "44c78fd4b8f49b434ac2ec28758d6cee29ba5b7563de1bf69407d0d499aff485"
}
```

## reachable-safety:candidate
reject; major/severe code_safety concretely identifies reachable return a[4] from length3 array (legal0..2).
原始目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
材料摘要：ece85986089f110d40824542ab06b0c1b877a9d7dee81e0f866da595bb280dd3
wire摘要：3d22574ccc7fbd88c72f08b95ff5ec516acbc4f4881e75e23701069b41f5ab25
```json
{
  "binding": {
    "owner_id": "36c15e68-e622-5af6-acd2-973e8f15e0bf",
    "unit_id": "542ac088-e850-562d-b015-1602447ea228",
    "operation_id": "31c5e375-b598-5891-8367-7887348974b2",
    "plan_id": "59748722-d12b-5950-a136-fafe5be8f6c5",
    "plan_version": 1,
    "plan_digest": "ccb45b98baf66a17044496e86e13d9cbca29e0bad35660c9dce3d90a55cca532",
    "input_digest": "e7bdf346a7566983dabf73640b176819a5f8b8018c02f1d11753de9ada0b7691",
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
          "operation": "遍历i=0,1,2并累加a[i]",
          "expected_state": "total依次为2,7,16",
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
      "resource_id": "f480e6da-844d-5483-9dbf-91c6c8bbdac2",
      "role": "explanation",
      "envelope": {
        "resource_type": "explanation",
        "prompt_version": "learning-resources-v1",
        "content": {
          "markdown": "a={2,5,9}，容量3，下标0、1、2。total初始为0。i=0读取a[0]=2后total=2；i=1读取a[1]=5后total=7；i=2读取a[2]=9后total=16。i增至3，i<3为假，停止循环，不访问a[3]，循环体恰执行3次。sum()返回16，不直接打印。"
        }
      },
      "content_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
      "dependency_digest": "518040ffa9131a24cc802efec0075c721577e1fab0f370752ab39ebe31fe9b9e",
      "upstream": []
    },
    {
      "resource_id": "5f250662-82b2-5b7b-a97a-0c305554eefe",
      "role": "code",
      "envelope": {
        "resource_type": "code",
        "prompt_version": "learning-resources-v1",
        "content": {
          "language": "C",
          "source": "#include <stddef.h>\nint sum(void){int a[3]={2,5,9};return a[4];}",
          "expected_output": "不打印；由调用方取得返回值。",
          "key_steps": [
            "total从0开始依次变为2、7、16。",
            "i=3时i<3为假，停止且不访问a[3]。"
          ],
          "display_only": true
        }
      },
      "content_digest": "c65dcdad44e18d172d4eb0894a8ed0828a1957c73e7f97cd3c882059f394b1a5",
      "dependency_digest": "65c66040903700cda8f766cc9a30d4c4a5ef86bc6aa82caf8d926f5e14706932",
      "upstream": [
        {
          "resource_id": "f480e6da-844d-5483-9dbf-91c6c8bbdac2",
          "content_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
          "dependency_digest": "518040ffa9131a24cc802efec0075c721577e1fab0f370752ab39ebe31fe9b9e"
        }
      ]
    },
    {
      "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
      "role": "exercise",
      "envelope": {
        "resource_type": "exercise",
        "prompt_version": "learning-resources-v1",
        "content": {
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
      },
      "content_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
      "dependency_digest": "7df9676d906591deb0d7595b88c6ede50a0f2047d150e4bb595925cf7e36f259",
      "upstream": [
        {
          "resource_id": "f480e6da-844d-5483-9dbf-91c6c8bbdac2",
          "content_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
          "dependency_digest": "518040ffa9131a24cc802efec0075c721577e1fab0f370752ab39ebe31fe9b9e"
        },
        {
          "resource_id": "5f250662-82b2-5b7b-a97a-0c305554eefe",
          "content_digest": "c65dcdad44e18d172d4eb0894a8ed0828a1957c73e7f97cd3c882059f394b1a5",
          "dependency_digest": "65c66040903700cda8f766cc9a30d4c4a5ef86bc6aa82caf8d926f5e14706932"
        }
      ]
    }
  ],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "scene_id": "a5e12946-57b8-53a3-8a40-7f05e814b615",
      "scene_version": 1,
      "resource_id": "f480e6da-844d-5483-9dbf-91c6c8bbdac2",
      "resource_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
      "dependency_digest": "518040ffa9131a24cc802efec0075c721577e1fab0f370752ab39ebe31fe9b9e"
    },
    {
      "role": "code",
      "scene_key": "code",
      "scene_id": "226303aa-753c-5568-8561-dcea38665965",
      "scene_version": 1,
      "resource_id": "5f250662-82b2-5b7b-a97a-0c305554eefe",
      "resource_digest": "c65dcdad44e18d172d4eb0894a8ed0828a1957c73e7f97cd3c882059f394b1a5",
      "dependency_digest": "65c66040903700cda8f766cc9a30d4c4a5ef86bc6aa82caf8d926f5e14706932"
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "scene_id": "9428d252-59aa-5ada-ab10-c33dd9bfb7fc",
      "scene_version": 1,
      "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
      "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
      "dependency_digest": "7df9676d906591deb0d7595b88c6ede50a0f2047d150e4bb595925cf7e36f259"
    }
  ],
  "actions": {
    "version": "teaching-actions-v1",
    "actions": [
      {
        "kind": "show_resource",
        "scene_key": "explanation",
        "resource_id": "f480e6da-844d-5483-9dbf-91c6c8bbdac2",
        "resource_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1"
      },
      {
        "kind": "show_resource",
        "scene_key": "code",
        "resource_id": "5f250662-82b2-5b7b-a97a-0c305554eefe",
        "resource_digest": "c65dcdad44e18d172d4eb0894a8ed0828a1957c73e7f97cd3c882059f394b1a5"
      },
      {
        "kind": "highlight",
        "scene_key": "code",
        "resource_id": "5f250662-82b2-5b7b-a97a-0c305554eefe",
        "resource_digest": "c65dcdad44e18d172d4eb0894a8ed0828a1957c73e7f97cd3c882059f394b1a5",
        "anchor_id": "a3"
      },
      {
        "kind": "highlight",
        "scene_key": "code",
        "resource_id": "5f250662-82b2-5b7b-a97a-0c305554eefe",
        "resource_digest": "c65dcdad44e18d172d4eb0894a8ed0828a1957c73e7f97cd3c882059f394b1a5",
        "anchor_id": "a4"
      },
      {
        "kind": "show_resource",
        "scene_key": "exercise",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "exercise_id": "q1"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "exercise_id": "q2"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "exercise_id": "q3"
      }
    ],
    "anchor_catalog": [
      {
        "anchor_id": "a1",
        "resource_id": "f480e6da-844d-5483-9dbf-91c6c8bbdac2",
        "resource_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
        "json_pointer": "/markdown",
        "start_utf8": 0,
        "end_utf8": 256
      },
      {
        "anchor_id": "a2",
        "resource_id": "5f250662-82b2-5b7b-a97a-0c305554eefe",
        "resource_digest": "c65dcdad44e18d172d4eb0894a8ed0828a1957c73e7f97cd3c882059f394b1a5",
        "json_pointer": "/expected_output",
        "start_utf8": 0,
        "end_utf8": 42
      },
      {
        "anchor_id": "a3",
        "resource_id": "5f250662-82b2-5b7b-a97a-0c305554eefe",
        "resource_digest": "c65dcdad44e18d172d4eb0894a8ed0828a1957c73e7f97cd3c882059f394b1a5",
        "json_pointer": "/key_steps/0",
        "start_utf8": 0,
        "end_utf8": 40
      },
      {
        "anchor_id": "a4",
        "resource_id": "5f250662-82b2-5b7b-a97a-0c305554eefe",
        "resource_digest": "c65dcdad44e18d172d4eb0894a8ed0828a1957c73e7f97cd3c882059f394b1a5",
        "json_pointer": "/key_steps/1",
        "start_utf8": 0,
        "end_utf8": 43
      },
      {
        "anchor_id": "a5",
        "resource_id": "5f250662-82b2-5b7b-a97a-0c305554eefe",
        "resource_digest": "c65dcdad44e18d172d4eb0894a8ed0828a1957c73e7f97cd3c882059f394b1a5",
        "json_pointer": "/language",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a6",
        "resource_id": "5f250662-82b2-5b7b-a97a-0c305554eefe",
        "resource_digest": "c65dcdad44e18d172d4eb0894a8ed0828a1957c73e7f97cd3c882059f394b1a5",
        "json_pointer": "/source",
        "start_utf8": 0,
        "end_utf8": 64
      },
      {
        "anchor_id": "a7",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a8",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/explanation",
        "start_utf8": 0,
        "end_utf8": 46
      },
      {
        "anchor_id": "a9",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a10",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/question",
        "start_utf8": 0,
        "end_utf8": 85
      },
      {
        "anchor_id": "a11",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a12",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/explanation",
        "start_utf8": 0,
        "end_utf8": 52
      },
      {
        "anchor_id": "a13",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a14",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/question",
        "start_utf8": 0,
        "end_utf8": 91
      },
      {
        "anchor_id": "a15",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a16",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/explanation",
        "start_utf8": 0,
        "end_utf8": 57
      },
      {
        "anchor_id": "a17",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a18",
        "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/question",
        "start_utf8": 0,
        "end_utf8": 88
      }
    ],
    "digest": "5068d04d88f0c8e61fdc59eaba680a6a3ff53c4fbc7e098f1e46f76eaa44a03b"
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
  "unit_digest": "6a4f42a8d7252ab845f5327418f6cffcddc49580a66bed3ad3711f8ee58c5523"
}
```

## gap-and-safety:candidate
reject; retain major/severe a[4] code_safety even with real teaching/measurement gap, never downgrade all to human.
原始目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
材料摘要：967b1960d24d8fd78ad6217ebafb7a04c4bedd881791983390ac394371804720
wire摘要：10724001648371bb45e03a4790d2918d1939aecda2ba0f19a9b771ef96ae1516
```json
{
  "binding": {
    "owner_id": "99169427-90bf-5721-a37a-48372599f1e2",
    "unit_id": "7e46740b-c5bf-5d4a-a55a-7521c26d3a90",
    "operation_id": "645a8bdc-4308-5501-a8dc-7bca375ab52e",
    "plan_id": "181570cb-794c-5d9e-ac2a-321695be8db0",
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
      "resource_id": "b670cd73-ffb4-50c1-90b7-fc36386cdd9d",
      "role": "explanation",
      "envelope": {
        "resource_type": "explanation",
        "prompt_version": "learning-resources-v1",
        "content": {
          "markdown": "a={2,5,9}，容量3，下标0、1、2。sum()返回16，不直接打印。"
        }
      },
      "content_digest": "2d21823e29bd9139d109a5436b13ef37487914c57636405a88be2e1b53d7d942",
      "dependency_digest": "7c06282d43d4bf1e414781ebf8034fd38704bd75ff60e39655fd777466086a3a",
      "upstream": []
    },
    {
      "resource_id": "2d320616-5af2-5613-9dbd-a21cc1ab9e93",
      "role": "code",
      "envelope": {
        "resource_type": "code",
        "prompt_version": "learning-resources-v1",
        "content": {
          "language": "C",
          "source": "#include <stddef.h>\nint sum(void){int a[3]={2,5,9};return a[4];}",
          "expected_output": "不打印；由调用方取得返回值。",
          "key_steps": [
            "遍历并求和后返回结果。"
          ],
          "display_only": true
        }
      },
      "content_digest": "5ff2d1fb4313120b35f4faefa629da7f5b2f2b9595135159a0c5a18dcbba5153",
      "dependency_digest": "788e95fc303e515f4dcfc3df0bded7da25fbecd4faabaf6716240225a4c14ed0",
      "upstream": [
        {
          "resource_id": "b670cd73-ffb4-50c1-90b7-fc36386cdd9d",
          "content_digest": "2d21823e29bd9139d109a5436b13ef37487914c57636405a88be2e1b53d7d942",
          "dependency_digest": "7c06282d43d4bf1e414781ebf8034fd38704bd75ff60e39655fd777466086a3a"
        }
      ]
    },
    {
      "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
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
      "dependency_digest": "63eeac10b88a75e774dfdfb1b516efffd16d8fbb081eafbc99139eb99fdf52e1",
      "upstream": [
        {
          "resource_id": "b670cd73-ffb4-50c1-90b7-fc36386cdd9d",
          "content_digest": "2d21823e29bd9139d109a5436b13ef37487914c57636405a88be2e1b53d7d942",
          "dependency_digest": "7c06282d43d4bf1e414781ebf8034fd38704bd75ff60e39655fd777466086a3a"
        },
        {
          "resource_id": "2d320616-5af2-5613-9dbd-a21cc1ab9e93",
          "content_digest": "5ff2d1fb4313120b35f4faefa629da7f5b2f2b9595135159a0c5a18dcbba5153",
          "dependency_digest": "788e95fc303e515f4dcfc3df0bded7da25fbecd4faabaf6716240225a4c14ed0"
        }
      ]
    }
  ],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "scene_id": "64810071-dac7-5e18-bc83-009adc1a433d",
      "scene_version": 1,
      "resource_id": "b670cd73-ffb4-50c1-90b7-fc36386cdd9d",
      "resource_digest": "2d21823e29bd9139d109a5436b13ef37487914c57636405a88be2e1b53d7d942",
      "dependency_digest": "7c06282d43d4bf1e414781ebf8034fd38704bd75ff60e39655fd777466086a3a"
    },
    {
      "role": "code",
      "scene_key": "code",
      "scene_id": "2b5cbd27-1b06-5afa-9467-478997bade86",
      "scene_version": 1,
      "resource_id": "2d320616-5af2-5613-9dbd-a21cc1ab9e93",
      "resource_digest": "5ff2d1fb4313120b35f4faefa629da7f5b2f2b9595135159a0c5a18dcbba5153",
      "dependency_digest": "788e95fc303e515f4dcfc3df0bded7da25fbecd4faabaf6716240225a4c14ed0"
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "scene_id": "ba756c62-6e36-581f-9ed5-872ce1a89e87",
      "scene_version": 1,
      "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
      "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
      "dependency_digest": "63eeac10b88a75e774dfdfb1b516efffd16d8fbb081eafbc99139eb99fdf52e1"
    }
  ],
  "actions": {
    "version": "teaching-actions-v1",
    "actions": [
      {
        "kind": "show_resource",
        "scene_key": "explanation",
        "resource_id": "b670cd73-ffb4-50c1-90b7-fc36386cdd9d",
        "resource_digest": "2d21823e29bd9139d109a5436b13ef37487914c57636405a88be2e1b53d7d942"
      },
      {
        "kind": "show_resource",
        "scene_key": "code",
        "resource_id": "2d320616-5af2-5613-9dbd-a21cc1ab9e93",
        "resource_digest": "5ff2d1fb4313120b35f4faefa629da7f5b2f2b9595135159a0c5a18dcbba5153"
      },
      {
        "kind": "highlight",
        "scene_key": "code",
        "resource_id": "2d320616-5af2-5613-9dbd-a21cc1ab9e93",
        "resource_digest": "5ff2d1fb4313120b35f4faefa629da7f5b2f2b9595135159a0c5a18dcbba5153",
        "anchor_id": "a3"
      },
      {
        "kind": "show_resource",
        "scene_key": "exercise",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "exercise_id": "q1"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "exercise_id": "q2"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "exercise_id": "q3"
      }
    ],
    "anchor_catalog": [
      {
        "anchor_id": "a1",
        "resource_id": "b670cd73-ffb4-50c1-90b7-fc36386cdd9d",
        "resource_digest": "2d21823e29bd9139d109a5436b13ef37487914c57636405a88be2e1b53d7d942",
        "json_pointer": "/markdown",
        "start_utf8": 0,
        "end_utf8": 74
      },
      {
        "anchor_id": "a2",
        "resource_id": "2d320616-5af2-5613-9dbd-a21cc1ab9e93",
        "resource_digest": "5ff2d1fb4313120b35f4faefa629da7f5b2f2b9595135159a0c5a18dcbba5153",
        "json_pointer": "/expected_output",
        "start_utf8": 0,
        "end_utf8": 42
      },
      {
        "anchor_id": "a3",
        "resource_id": "2d320616-5af2-5613-9dbd-a21cc1ab9e93",
        "resource_digest": "5ff2d1fb4313120b35f4faefa629da7f5b2f2b9595135159a0c5a18dcbba5153",
        "json_pointer": "/key_steps/0",
        "start_utf8": 0,
        "end_utf8": 33
      },
      {
        "anchor_id": "a4",
        "resource_id": "2d320616-5af2-5613-9dbd-a21cc1ab9e93",
        "resource_digest": "5ff2d1fb4313120b35f4faefa629da7f5b2f2b9595135159a0c5a18dcbba5153",
        "json_pointer": "/language",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a5",
        "resource_id": "2d320616-5af2-5613-9dbd-a21cc1ab9e93",
        "resource_digest": "5ff2d1fb4313120b35f4faefa629da7f5b2f2b9595135159a0c5a18dcbba5153",
        "json_pointer": "/source",
        "start_utf8": 0,
        "end_utf8": 64
      },
      {
        "anchor_id": "a6",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/0/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a7",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/0/explanation",
        "start_utf8": 0,
        "end_utf8": 41
      },
      {
        "anchor_id": "a8",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/0/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a9",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/0/question",
        "start_utf8": 0,
        "end_utf8": 97
      },
      {
        "anchor_id": "a10",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/1/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a11",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/1/explanation",
        "start_utf8": 0,
        "end_utf8": 17
      },
      {
        "anchor_id": "a12",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/1/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a13",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/1/question",
        "start_utf8": 0,
        "end_utf8": 62
      },
      {
        "anchor_id": "a14",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/2/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a15",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/2/explanation",
        "start_utf8": 0,
        "end_utf8": 54
      },
      {
        "anchor_id": "a16",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/2/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a17",
        "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
        "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
        "json_pointer": "/items/2/question",
        "start_utf8": 0,
        "end_utf8": 90
      }
    ],
    "digest": "880d9112349461015ba08440eab31c0475b143b08610356611d21b2efacbb6bd"
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
  "unit_digest": "a0386a79ab9eac2dca63989d7b56f12befcc61f7a2f20b96a6bc31fd71d5de87"
}
```

## trace-complete:candidate
pass with five required checks and no findings/unchecked/unresolved or attached false positives.
原始目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
材料摘要：e422c5a587b691edb34e26de69d40562e601276b0b91ebd069db8e231c3a0701
wire摘要：1311972347f9a952ab44e874bf57aa7535359df8ff0c98748fc949a3d08e2a4c
```json
{
  "binding": {
    "owner_id": "d0e19f6d-49dd-5666-a1e4-327562f44d14",
    "unit_id": "216bb2d3-1eca-5f70-a2a8-b794d7767e0c",
    "operation_id": "3ca8842e-0ee8-5d20-a5e3-340846dcb0a7",
    "plan_id": "fbf98bcd-5b14-58e8-9583-a5ca044a0e1d",
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
      "resource_id": "9ce4bd78-67e5-5cd0-bcc1-4bee43a411c6",
      "role": "explanation",
      "envelope": {
        "resource_type": "explanation",
        "prompt_version": "learning-resources-v1",
        "content": {
          "markdown": "a={2,5,9}，容量3，下标0、1、2。total初始为0。i=0读取a[0]=2后total=2；i=1读取a[1]=5后total=7；i=2读取a[2]=9后total=16。i增至3，i<3为假，停止循环，不访问a[3]，循环体恰执行3次。sum()返回16，不直接打印。"
        }
      },
      "content_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
      "dependency_digest": "ade5a7075ae6fbfcc05535b67d4d168fb444004f782a3c4992a6b5309079741f",
      "upstream": []
    },
    {
      "resource_id": "262a874d-875b-57db-bc1a-f70906f964f5",
      "role": "code",
      "envelope": {
        "resource_type": "code",
        "prompt_version": "learning-resources-v1",
        "content": {
          "language": "C",
          "source": "#include <stddef.h>\nint sum(void){int a[3]={2,5,9};int total=0;for(int i=0;i<3;i++)total+=a[i];return total;}",
          "expected_output": "不打印；由调用方取得返回值。",
          "key_steps": [
            "total从0开始依次变为2、7、16。",
            "i=3时i<3为假，停止且不访问a[3]。"
          ],
          "display_only": true
        }
      },
      "content_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
      "dependency_digest": "28cc60942460f1f1149f33a81db2cf62be94a3971fd32f7e10bb91e008077f18",
      "upstream": [
        {
          "resource_id": "9ce4bd78-67e5-5cd0-bcc1-4bee43a411c6",
          "content_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
          "dependency_digest": "ade5a7075ae6fbfcc05535b67d4d168fb444004f782a3c4992a6b5309079741f"
        }
      ]
    },
    {
      "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
      "role": "exercise",
      "envelope": {
        "resource_type": "exercise",
        "prompt_version": "learning-resources-v1",
        "content": {
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
      },
      "content_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
      "dependency_digest": "d6189af9110715a16db81dc7552adf3fa7c735cf16841df0d50f7ee0283acc4d",
      "upstream": [
        {
          "resource_id": "9ce4bd78-67e5-5cd0-bcc1-4bee43a411c6",
          "content_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
          "dependency_digest": "ade5a7075ae6fbfcc05535b67d4d168fb444004f782a3c4992a6b5309079741f"
        },
        {
          "resource_id": "262a874d-875b-57db-bc1a-f70906f964f5",
          "content_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
          "dependency_digest": "28cc60942460f1f1149f33a81db2cf62be94a3971fd32f7e10bb91e008077f18"
        }
      ]
    }
  ],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "scene_id": "20920dc3-9ef9-55a3-b96c-e65433021b87",
      "scene_version": 1,
      "resource_id": "9ce4bd78-67e5-5cd0-bcc1-4bee43a411c6",
      "resource_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
      "dependency_digest": "ade5a7075ae6fbfcc05535b67d4d168fb444004f782a3c4992a6b5309079741f"
    },
    {
      "role": "code",
      "scene_key": "code",
      "scene_id": "3e6781aa-1dd0-5f98-9490-3633d1fb1bed",
      "scene_version": 1,
      "resource_id": "262a874d-875b-57db-bc1a-f70906f964f5",
      "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
      "dependency_digest": "28cc60942460f1f1149f33a81db2cf62be94a3971fd32f7e10bb91e008077f18"
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "scene_id": "3fba255a-4a7c-545a-a1c8-336a78423748",
      "scene_version": 1,
      "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
      "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
      "dependency_digest": "d6189af9110715a16db81dc7552adf3fa7c735cf16841df0d50f7ee0283acc4d"
    }
  ],
  "actions": {
    "version": "teaching-actions-v1",
    "actions": [
      {
        "kind": "show_resource",
        "scene_key": "explanation",
        "resource_id": "9ce4bd78-67e5-5cd0-bcc1-4bee43a411c6",
        "resource_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1"
      },
      {
        "kind": "show_resource",
        "scene_key": "code",
        "resource_id": "262a874d-875b-57db-bc1a-f70906f964f5",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60"
      },
      {
        "kind": "highlight",
        "scene_key": "code",
        "resource_id": "262a874d-875b-57db-bc1a-f70906f964f5",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "anchor_id": "a3"
      },
      {
        "kind": "highlight",
        "scene_key": "code",
        "resource_id": "262a874d-875b-57db-bc1a-f70906f964f5",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "anchor_id": "a4"
      },
      {
        "kind": "show_resource",
        "scene_key": "exercise",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "exercise_id": "q1"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "exercise_id": "q2"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "exercise_id": "q3"
      }
    ],
    "anchor_catalog": [
      {
        "anchor_id": "a1",
        "resource_id": "9ce4bd78-67e5-5cd0-bcc1-4bee43a411c6",
        "resource_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
        "json_pointer": "/markdown",
        "start_utf8": 0,
        "end_utf8": 256
      },
      {
        "anchor_id": "a2",
        "resource_id": "262a874d-875b-57db-bc1a-f70906f964f5",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/expected_output",
        "start_utf8": 0,
        "end_utf8": 42
      },
      {
        "anchor_id": "a3",
        "resource_id": "262a874d-875b-57db-bc1a-f70906f964f5",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/key_steps/0",
        "start_utf8": 0,
        "end_utf8": 40
      },
      {
        "anchor_id": "a4",
        "resource_id": "262a874d-875b-57db-bc1a-f70906f964f5",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/key_steps/1",
        "start_utf8": 0,
        "end_utf8": 43
      },
      {
        "anchor_id": "a5",
        "resource_id": "262a874d-875b-57db-bc1a-f70906f964f5",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/language",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a6",
        "resource_id": "262a874d-875b-57db-bc1a-f70906f964f5",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/source",
        "start_utf8": 0,
        "end_utf8": 109
      },
      {
        "anchor_id": "a7",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a8",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/explanation",
        "start_utf8": 0,
        "end_utf8": 46
      },
      {
        "anchor_id": "a9",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a10",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/question",
        "start_utf8": 0,
        "end_utf8": 85
      },
      {
        "anchor_id": "a11",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a12",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/explanation",
        "start_utf8": 0,
        "end_utf8": 52
      },
      {
        "anchor_id": "a13",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a14",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/question",
        "start_utf8": 0,
        "end_utf8": 91
      },
      {
        "anchor_id": "a15",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a16",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/explanation",
        "start_utf8": 0,
        "end_utf8": 57
      },
      {
        "anchor_id": "a17",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a18",
        "resource_id": "fd6d0e4f-245f-528f-8a81-64b8cc35cfff",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/question",
        "start_utf8": 0,
        "end_utf8": 88
      }
    ],
    "digest": "63ca99c11eb5b2c540788910146a5fbe351cfc82b0c2e2817f7738b720576f93"
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
  "unit_digest": "9f8c3237f53d5b83f776eed076d42c110e7dcef6c43d091d980ed6ca4238ca66"
}
```
