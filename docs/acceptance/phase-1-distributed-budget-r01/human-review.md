# 单例预算验证：分散覆盖low，只调总输出上限至8192

预算/标签尚未绑定批准。最多一次，成功或失败后都停止，不测试其他样本。
判据保持：pass且无finding/unchecked/unresolved，无附带误报；具体语义需实际人工核对。
目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。
材料摘要：87bcc0bc29edb86451809aedc204f15d4defa5813190a5aeb6961d08075f2d04
本次wire摘要：7b8ad2813f260f67fac1cf22da984783be8a36c2269c18ad1fc9eb0f0b07a509
```json
{
  "binding": {
    "owner_id": "619a5bf8-9bcf-512c-8754-ca639dfca68e",
    "unit_id": "de5e99d1-a047-5575-ab2b-e3db3da3551f",
    "operation_id": "1f948b2e-0696-57a5-bbc9-f648c297c6b2",
    "plan_id": "40790e97-aefb-52ba-b012-4813ee4d1210",
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
      "resource_id": "8563b525-1738-57ff-891f-ef06a12f31cf",
      "role": "explanation",
      "envelope": {
        "resource_type": "explanation",
        "prompt_version": "learning-resources-v1",
        "content": {
          "markdown": "固定输入a={2,5,9}；sum无外部参数，返回16，不直接打印。"
        }
      },
      "content_digest": "01d6df0d4dc67677f5d2bd0952ce8ebd49bf422e34ff10ba821490b7d461d94e",
      "dependency_digest": "52d063a36c6a1e31fb9c964276585dabaeb09b9b79cfdaf7685c6f18a8a049b5",
      "upstream": []
    },
    {
      "resource_id": "6bbc6537-ba3b-5725-9d19-ed7bceb84eef",
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
      "dependency_digest": "e9a8e895403550426f3c0b7f925ad1960c95a5f63fccd9357f2053c60cc8e85e",
      "upstream": [
        {
          "resource_id": "8563b525-1738-57ff-891f-ef06a12f31cf",
          "content_digest": "01d6df0d4dc67677f5d2bd0952ce8ebd49bf422e34ff10ba821490b7d461d94e",
          "dependency_digest": "52d063a36c6a1e31fb9c964276585dabaeb09b9b79cfdaf7685c6f18a8a049b5"
        }
      ]
    },
    {
      "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
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
      "dependency_digest": "3a9b75b5fa996ee34c6b74e8067b9d30dbfd21edff79e2a44ce7cb02f45407a8",
      "upstream": [
        {
          "resource_id": "8563b525-1738-57ff-891f-ef06a12f31cf",
          "content_digest": "01d6df0d4dc67677f5d2bd0952ce8ebd49bf422e34ff10ba821490b7d461d94e",
          "dependency_digest": "52d063a36c6a1e31fb9c964276585dabaeb09b9b79cfdaf7685c6f18a8a049b5"
        },
        {
          "resource_id": "6bbc6537-ba3b-5725-9d19-ed7bceb84eef",
          "content_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
          "dependency_digest": "e9a8e895403550426f3c0b7f925ad1960c95a5f63fccd9357f2053c60cc8e85e"
        }
      ]
    }
  ],
  "scenes": [
    {
      "role": "explanation",
      "scene_key": "explanation",
      "scene_id": "7e6937bd-52d7-5c6c-9fc8-3b01a7ab4f55",
      "scene_version": 1,
      "resource_id": "8563b525-1738-57ff-891f-ef06a12f31cf",
      "resource_digest": "01d6df0d4dc67677f5d2bd0952ce8ebd49bf422e34ff10ba821490b7d461d94e",
      "dependency_digest": "52d063a36c6a1e31fb9c964276585dabaeb09b9b79cfdaf7685c6f18a8a049b5"
    },
    {
      "role": "code",
      "scene_key": "code",
      "scene_id": "1f458187-a26c-594a-9e7b-fbe7926b334b",
      "scene_version": 1,
      "resource_id": "6bbc6537-ba3b-5725-9d19-ed7bceb84eef",
      "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
      "dependency_digest": "e9a8e895403550426f3c0b7f925ad1960c95a5f63fccd9357f2053c60cc8e85e"
    },
    {
      "role": "exercise",
      "scene_key": "exercise",
      "scene_id": "470bbeb4-5bfe-5f72-a915-628cbf052e66",
      "scene_version": 1,
      "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
      "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
      "dependency_digest": "3a9b75b5fa996ee34c6b74e8067b9d30dbfd21edff79e2a44ce7cb02f45407a8"
    }
  ],
  "actions": {
    "version": "teaching-actions-v1",
    "actions": [
      {
        "kind": "show_resource",
        "scene_key": "explanation",
        "resource_id": "8563b525-1738-57ff-891f-ef06a12f31cf",
        "resource_digest": "01d6df0d4dc67677f5d2bd0952ce8ebd49bf422e34ff10ba821490b7d461d94e"
      },
      {
        "kind": "show_resource",
        "scene_key": "code",
        "resource_id": "6bbc6537-ba3b-5725-9d19-ed7bceb84eef",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60"
      },
      {
        "kind": "highlight",
        "scene_key": "code",
        "resource_id": "6bbc6537-ba3b-5725-9d19-ed7bceb84eef",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "anchor_id": "a3"
      },
      {
        "kind": "highlight",
        "scene_key": "code",
        "resource_id": "6bbc6537-ba3b-5725-9d19-ed7bceb84eef",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "anchor_id": "a4"
      },
      {
        "kind": "show_resource",
        "scene_key": "exercise",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "exercise_id": "q1"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "exercise_id": "q2"
      },
      {
        "kind": "ask_exercise",
        "scene_key": "exercise",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "exercise_id": "q3"
      }
    ],
    "anchor_catalog": [
      {
        "anchor_id": "a1",
        "resource_id": "8563b525-1738-57ff-891f-ef06a12f31cf",
        "resource_digest": "01d6df0d4dc67677f5d2bd0952ce8ebd49bf422e34ff10ba821490b7d461d94e",
        "json_pointer": "/markdown",
        "start_utf8": 0,
        "end_utf8": 74
      },
      {
        "anchor_id": "a2",
        "resource_id": "6bbc6537-ba3b-5725-9d19-ed7bceb84eef",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/expected_output",
        "start_utf8": 0,
        "end_utf8": 42
      },
      {
        "anchor_id": "a3",
        "resource_id": "6bbc6537-ba3b-5725-9d19-ed7bceb84eef",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/key_steps/0",
        "start_utf8": 0,
        "end_utf8": 40
      },
      {
        "anchor_id": "a4",
        "resource_id": "6bbc6537-ba3b-5725-9d19-ed7bceb84eef",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/key_steps/1",
        "start_utf8": 0,
        "end_utf8": 43
      },
      {
        "anchor_id": "a5",
        "resource_id": "6bbc6537-ba3b-5725-9d19-ed7bceb84eef",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/language",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a6",
        "resource_id": "6bbc6537-ba3b-5725-9d19-ed7bceb84eef",
        "resource_digest": "281f23f8b481c1d8d5db61966fbc30d2b8ddb5bede539a5ad968e65c4f453b60",
        "json_pointer": "/source",
        "start_utf8": 0,
        "end_utf8": 109
      },
      {
        "anchor_id": "a7",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a8",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/explanation",
        "start_utf8": 0,
        "end_utf8": 46
      },
      {
        "anchor_id": "a9",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a10",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/0/question",
        "start_utf8": 0,
        "end_utf8": 85
      },
      {
        "anchor_id": "a11",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a12",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/explanation",
        "start_utf8": 0,
        "end_utf8": 52
      },
      {
        "anchor_id": "a13",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a14",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/1/question",
        "start_utf8": 0,
        "end_utf8": 91
      },
      {
        "anchor_id": "a15",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/answer",
        "start_utf8": 0,
        "end_utf8": 1
      },
      {
        "anchor_id": "a16",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/explanation",
        "start_utf8": 0,
        "end_utf8": 57
      },
      {
        "anchor_id": "a17",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/id",
        "start_utf8": 0,
        "end_utf8": 2
      },
      {
        "anchor_id": "a18",
        "resource_id": "ec94c2dd-6b4b-50ff-a122-6ef201fa5a7f",
        "resource_digest": "7eaf610d07dab1bbf97bb61cfe62e30b920cdc9fa3dc7833b2ce17e50a627a35",
        "json_pointer": "/items/2/question",
        "start_utf8": 0,
        "end_utf8": 88
      }
    ],
    "digest": "aefa4ea0f50116f0417307777fb49f89f975cdaef8fe39b4138d9b114f77ca18"
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
  "unit_digest": "34d895dc4588d234484feb853ab0aced60d6aa7fec96cea485260995e4a72fab"
}
```
