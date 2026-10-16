# v4.5四例：冻结学生材料与三项人工判据

尚未绑定真实预算/标签批准；完整性、全部断言、全部引用任一失败即停。

## reachable-safety:candidate
reject severe/major code_safety for length3 a4; all additional claims must be supported, no deterministic UB return/outcome; every anchor must support its corresponding argument.
原始目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
材料摘要：9863bb68c355eea9dd1c269a5be29e06d734b530cce3b279500edf18f06a4c90
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
    "policy_digest": "13439cff15345af5adca3ecf12cd9a75dfa07e999bb1fd211681c068c455c013"
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
      "dependency_digest": "d51a3c88a2921c4ed761aac3db55200af8ff3538a8628a6648706b02fd3a78ad",
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
      "dependency_digest": "61f01f0fbb858f1853bbac5480d90132e2a97a2103565cc015ecd632317239b1",
      "upstream": [
        {
          "resource_id": "f480e6da-844d-5483-9dbf-91c6c8bbdac2",
          "content_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
          "dependency_digest": "d51a3c88a2921c4ed761aac3db55200af8ff3538a8628a6648706b02fd3a78ad"
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
      "dependency_digest": "c6366299ef6ab8c9475d134569579642e7f1bbc4a1d76ed82bbd6bfe0ef51e4c",
      "upstream": [
        {
          "resource_id": "f480e6da-844d-5483-9dbf-91c6c8bbdac2",
          "content_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
          "dependency_digest": "d51a3c88a2921c4ed761aac3db55200af8ff3538a8628a6648706b02fd3a78ad"
        },
        {
          "resource_id": "5f250662-82b2-5b7b-a97a-0c305554eefe",
          "content_digest": "c65dcdad44e18d172d4eb0894a8ed0828a1957c73e7f97cd3c882059f394b1a5",
          "dependency_digest": "61f01f0fbb858f1853bbac5480d90132e2a97a2103565cc015ecd632317239b1"
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
      "dependency_digest": "d51a3c88a2921c4ed761aac3db55200af8ff3538a8628a6648706b02fd3a78ad"
    },
    {
      "role": "code",
      "scene_key": "code",
      "scene_id": "226303aa-753c-5568-8561-dcea38665965",
      "scene_version": 1,
      "resource_id": "5f250662-82b2-5b7b-a97a-0c305554eefe",
      "resource_digest": "c65dcdad44e18d172d4eb0894a8ed0828a1957c73e7f97cd3c882059f394b1a5",
      "dependency_digest": "61f01f0fbb858f1853bbac5480d90132e2a97a2103565cc015ecd632317239b1"
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "scene_id": "9428d252-59aa-5ada-ab10-c33dd9bfb7fc",
      "scene_version": 1,
      "resource_id": "fff349a7-9caa-55bd-859b-ca904ada4f8a",
      "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
      "dependency_digest": "c6366299ef6ab8c9475d134569579642e7f1bbc4a1d76ed82bbd6bfe0ef51e4c"
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
  "unit_digest": "6c24e1d0894da8cd190d590dee5051bbc420e5b32a8b4f6c269f9bb19d168a3d"
}
```

## fact-contradiction:candidate
reject major/severe fact for return18 versus actual16; every main/secondary anchor must support the argument, no borrowing adjacent fields or accepting a15/F as numeric evidence.
原始目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
材料摘要：a18523040fc2de2da6458e0fbbe8f0e22ca26915da6614866d1927166078775b
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
    "policy_digest": "13439cff15345af5adca3ecf12cd9a75dfa07e999bb1fd211681c068c455c013"
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
      "dependency_digest": "a5ac2441bf02ef989de113461f98f3eceade35dadb4e51cf11b933a20e06e0a0",
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
      "dependency_digest": "a4c97c72971792f9be275d0e728a5a4c01fbdf11a39baea5c50862cbe98f586e",
      "upstream": [
        {
          "resource_id": "fccaefd9-fcc8-56c4-8e67-4242f35be50d",
          "content_digest": "aabfa9dbf8c9eb7914528cb1f94c7154432e47415d5e6e139b775fd513830450",
          "dependency_digest": "a5ac2441bf02ef989de113461f98f3eceade35dadb4e51cf11b933a20e06e0a0"
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
      "dependency_digest": "6029ebf193d60b278a90a26e7500f10660e199a0df1caa994672e994b39749b5",
      "upstream": [
        {
          "resource_id": "fccaefd9-fcc8-56c4-8e67-4242f35be50d",
          "content_digest": "aabfa9dbf8c9eb7914528cb1f94c7154432e47415d5e6e139b775fd513830450",
          "dependency_digest": "a5ac2441bf02ef989de113461f98f3eceade35dadb4e51cf11b933a20e06e0a0"
        },
        {
          "resource_id": "58bb0ed5-8527-5ae3-a882-d0884fcf4391",
          "content_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
          "dependency_digest": "a4c97c72971792f9be275d0e728a5a4c01fbdf11a39baea5c50862cbe98f586e"
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
      "dependency_digest": "a5ac2441bf02ef989de113461f98f3eceade35dadb4e51cf11b933a20e06e0a0"
    },
    {
      "role": "code",
      "scene_key": "code",
      "scene_id": "2a7de0f6-da6a-51c2-b059-7738a40adf73",
      "scene_version": 1,
      "resource_id": "58bb0ed5-8527-5ae3-a882-d0884fcf4391",
      "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
      "dependency_digest": "a4c97c72971792f9be275d0e728a5a4c01fbdf11a39baea5c50862cbe98f586e"
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "scene_id": "5104e8f9-bf76-55ff-be3b-cf29a95a19d5",
      "scene_version": 1,
      "resource_id": "b5908630-ec02-59ad-85dd-5d678f28f068",
      "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
      "dependency_digest": "6029ebf193d60b278a90a26e7500f10660e199a0df1caa994672e994b39749b5"
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
  "unit_digest": "499503f92a411ed379c9fa9a2f0ae510ff9896d029a203321647eba75a250398"
}
```

## gap-and-safety:candidate
retain serious code_safety reject despite teaching gap; every other claim/citation accurate, no UB numerical inference.
原始目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
材料摘要：4aebcd62660a65ff26435d1574dbebdd84f6c7bf4252499fde62751720fbf8ae
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
    "policy_digest": "13439cff15345af5adca3ecf12cd9a75dfa07e999bb1fd211681c068c455c013"
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
      "dependency_digest": "a24eae2dd5b499b8784f57213cb2101486e440881e8806ee4cd02a6528760d9d",
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
      "dependency_digest": "86be278e88f238f3f0c2a92e23e710eb851714881d39e570d5d9642c9d23453e",
      "upstream": [
        {
          "resource_id": "b670cd73-ffb4-50c1-90b7-fc36386cdd9d",
          "content_digest": "2d21823e29bd9139d109a5436b13ef37487914c57636405a88be2e1b53d7d942",
          "dependency_digest": "a24eae2dd5b499b8784f57213cb2101486e440881e8806ee4cd02a6528760d9d"
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
      "dependency_digest": "0d37ec3aea69a5b8f7a17a87512489faf5360002ec13e37d2f780d6ebe4eaba8",
      "upstream": [
        {
          "resource_id": "b670cd73-ffb4-50c1-90b7-fc36386cdd9d",
          "content_digest": "2d21823e29bd9139d109a5436b13ef37487914c57636405a88be2e1b53d7d942",
          "dependency_digest": "a24eae2dd5b499b8784f57213cb2101486e440881e8806ee4cd02a6528760d9d"
        },
        {
          "resource_id": "2d320616-5af2-5613-9dbd-a21cc1ab9e93",
          "content_digest": "5ff2d1fb4313120b35f4faefa629da7f5b2f2b9595135159a0c5a18dcbba5153",
          "dependency_digest": "86be278e88f238f3f0c2a92e23e710eb851714881d39e570d5d9642c9d23453e"
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
      "dependency_digest": "a24eae2dd5b499b8784f57213cb2101486e440881e8806ee4cd02a6528760d9d"
    },
    {
      "role": "code",
      "scene_key": "code",
      "scene_id": "2b5cbd27-1b06-5afa-9467-478997bade86",
      "scene_version": 1,
      "resource_id": "2d320616-5af2-5613-9dbd-a21cc1ab9e93",
      "resource_digest": "5ff2d1fb4313120b35f4faefa629da7f5b2f2b9595135159a0c5a18dcbba5153",
      "dependency_digest": "86be278e88f238f3f0c2a92e23e710eb851714881d39e570d5d9642c9d23453e"
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "scene_id": "ba756c62-6e36-581f-9ed5-872ce1a89e87",
      "scene_version": 1,
      "resource_id": "73f045f1-0a18-5c20-a7d7-e85e5d973b6f",
      "resource_digest": "5ced6e9273f4e12291d42caabc894e7926912dc7a550609e76fce6ee9cd22b85",
      "dependency_digest": "0d37ec3aea69a5b8f7a17a87512489faf5360002ec13e37d2f780d6ebe4eaba8"
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
  "unit_digest": "26a41884f96e0671f73c01928b426629b8fea9c77c60914cdecf7848bb42cc90"
}
```

## trace-complete:candidate
pass with all five checks and empty findings/unchecked/unresolved, no false positives.
原始目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
材料摘要：3376bc1ea1b286867b9cfb1e27c54389c4cbb1f34798d15fafb82357fec2bcd9
```json
{
  "binding": {
    "owner_id": "6c25cba8-ec39-5dcf-ad9d-7e809118bd9f",
    "unit_id": "d36b7fc1-2c28-5e8f-ac99-903453b1d2b8",
    "operation_id": "858196c5-2ce6-53dc-9e12-f2d4707f49d5",
    "plan_id": "44652353-da15-552f-9a4b-a0da8c404869",
    "plan_version": 1,
    "plan_digest": "6e001c28456d4841817de40632d24d87c231159d61bf15f53d4c9ae57d07d8f1",
    "input_digest": "ef8f69cb35a786584eff9a40380be6cdae7e454f792b3424d78c99627083c4d9",
    "references_digest": "73c808e61d8d171633df56ec547afd4c0172facc4598782432d22880d9c8841c",
    "policy_version": "hybrid-review-v1",
    "policy_digest": "13439cff15345af5adca3ecf12cd9a75dfa07e999bb1fd211681c068c455c013"
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
      "resource_id": "becf7809-a6bf-5a4f-9eb2-702b46356109",
      "role": "explanation",
      "envelope": {
        "resource_type": "explanation",
        "prompt_version": "learning-resources-v1",
        "content": {
          "markdown": "a={2,5,9}，容量3，下标0、1、2。total初始为0。i=0读取a[0]=2后total=2；i=1读取a[1]=5后total=7；i=2读取a[2]=9后total=16。i增至3，i<3为假，停止循环，不访问a[3]，循环体恰执行3次。sum()返回16，不直接打印。"
        }
      },
      "content_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
      "dependency_digest": "25be89db392ca6954813c0c27546ba03cef68cb5b02012c77e60bf0a3cbd6613",
      "upstream": []
    },
    {
      "resource_id": "1eb4c005-c63b-51a3-bc6f-3a1c3c7a30f2",
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
      "dependency_digest": "3ae5694c72a83add56d7fccb0582fe51c4a14ba107189665599b6c9ecb38cdc8",
      "upstream": [
        {
          "resource_id": "becf7809-a6bf-5a4f-9eb2-702b46356109",
          "content_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
          "dependency_digest": "25be89db392ca6954813c0c27546ba03cef68cb5b02012c77e60bf0a3cbd6613"
        }
      ]
    },
    {
      "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
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
      "dependency_digest": "e4a1620c9eec2ddbf0b5d2eda8b99d3c5f30e86967651baa261e981c5b501acb",
      "upstream": [
        {
          "resource_id": "becf7809-a6bf-5a4f-9eb2-702b46356109",
          "content_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
          "dependency_digest": "25be89db392ca6954813c0c27546ba03cef68cb5b02012c77e60bf0a3cbd6613"
        },
        {
          "resource_id": "1eb4c005-c63b-51a3-bc6f-3a1c3c7a30f2",
          "content_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
          "dependency_digest": "3ae5694c72a83add56d7fccb0582fe51c4a14ba107189665599b6c9ecb38cdc8"
        }
      ]
    }
  ],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "scene_id": "abf5969c-39c1-562f-a8ce-7839e6f4b240",
      "scene_version": 1,
      "resource_id": "becf7809-a6bf-5a4f-9eb2-702b46356109",
      "resource_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
      "dependency_digest": "25be89db392ca6954813c0c27546ba03cef68cb5b02012c77e60bf0a3cbd6613"
    },
    {
      "role": "code",
      "scene_key": "code",
      "scene_id": "57f68268-e099-5c81-a694-0dcf92114f88",
      "scene_version": 1,
      "resource_id": "1eb4c005-c63b-51a3-bc6f-3a1c3c7a30f2",
      "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
      "dependency_digest": "3ae5694c72a83add56d7fccb0582fe51c4a14ba107189665599b6c9ecb38cdc8"
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "scene_id": "262e11ca-5e56-5a2c-8788-02c7d30dd25a",
      "scene_version": 1,
      "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
      "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
      "dependency_digest": "e4a1620c9eec2ddbf0b5d2eda8b99d3c5f30e86967651baa261e981c5b501acb"
    }
  ],
  "actions": {
    "version": "teaching-actions-v1",
    "actions": [
      {
        "kind": "show_resource",
        "scene_key": "explanation",
        "resource_id": "becf7809-a6bf-5a4f-9eb2-702b46356109",
        "resource_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1"
      },
      {
        "kind": "show_resource",
        "scene_key": "code",
        "resource_id": "1eb4c005-c63b-51a3-bc6f-3a1c3c7a30f2",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60"
      },
      {
        "kind": "highlight",
        "scene_key": "code",
        "resource_id": "1eb4c005-c63b-51a3-bc6f-3a1c3c7a30f2",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "anchor_id": "a3"
      },
      {
        "kind": "highlight",
        "scene_key": "code",
        "resource_id": "1eb4c005-c63b-51a3-bc6f-3a1c3c7a30f2",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "anchor_id": "a4"
      },
      {
        "kind": "show_resource",
        "scene_key": "exercise",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "exercise_id": "q1"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "exercise_id": "q2"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "exercise_id": "q3"
      }
    ],
    "anchor_catalog": [
      {
        "anchor_id": "a1",
        "resource_id": "becf7809-a6bf-5a4f-9eb2-702b46356109",
        "resource_digest": "b06705b2ef6a4d09590bae655dd3d91369808240bbb1164cd1751d0a0cb45fa1",
        "json_pointer": "/markdown",
        "start_utf8": 0,
        "end_utf8": 256
      },
      {
        "anchor_id": "a2",
        "resource_id": "1eb4c005-c63b-51a3-bc6f-3a1c3c7a30f2",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/expected_output",
        "start_utf8": 0,
        "end_utf8": 42
      },
      {
        "anchor_id": "a3",
        "resource_id": "1eb4c005-c63b-51a3-bc6f-3a1c3c7a30f2",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/key_steps/0",
        "start_utf8": 0,
        "end_utf8": 40
      },
      {
        "anchor_id": "a4",
        "resource_id": "1eb4c005-c63b-51a3-bc6f-3a1c3c7a30f2",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/key_steps/1",
        "start_utf8": 0,
        "end_utf8": 43
      },
      {
        "anchor_id": "a5",
        "resource_id": "1eb4c005-c63b-51a3-bc6f-3a1c3c7a30f2",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/language",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a6",
        "resource_id": "1eb4c005-c63b-51a3-bc6f-3a1c3c7a30f2",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/source",
        "start_utf8": 0,
        "end_utf8": 109
      },
      {
        "anchor_id": "a7",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a8",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/explanation",
        "start_utf8": 0,
        "end_utf8": 46
      },
      {
        "anchor_id": "a9",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a10",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/question",
        "start_utf8": 0,
        "end_utf8": 85
      },
      {
        "anchor_id": "a11",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a12",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/explanation",
        "start_utf8": 0,
        "end_utf8": 52
      },
      {
        "anchor_id": "a13",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a14",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/question",
        "start_utf8": 0,
        "end_utf8": 91
      },
      {
        "anchor_id": "a15",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a16",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/explanation",
        "start_utf8": 0,
        "end_utf8": 57
      },
      {
        "anchor_id": "a17",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a18",
        "resource_id": "e2a5fe7c-1490-5ee3-8463-318c3b5248a9",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/question",
        "start_utf8": 0,
        "end_utf8": 88
      }
    ],
    "digest": "28bd9f1adde43f130e048b038a7534ea57039dc8a69b4e4f975f4ee7423cf560"
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
  "unit_digest": "42c3510acaa867194089f76184104de67baa07dfce1ae61c9de93d78d8087e63"
}
```
