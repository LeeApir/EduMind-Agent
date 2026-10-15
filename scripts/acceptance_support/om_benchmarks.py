"""New assistant-authored audit fixtures, awaiting independent human ground truth.

C snippets are display-only and never compiled/executed by this preparation step.
Paired controls are intentionally related, not statistically independent draws.
"""

from copy import deepcopy

AUDIT_QUESTION = "[判断题] 审核应按明示前提逐步核对代码。"
AUDIT_QUESTION += "仅填 T 或 F（T=正确，F=错误）"

# node, precondition, faulty source, safe source, concrete counterexample
SAFETY = (
    (
        "array",
        "调用peek()；数组恰有3项。",
        "int peek(void){int a[3]={4,5,6};return a[3];}",
        "int peek(void){int a[3]={4,5,6};return a[2];}",
        "a[3]越过长度3数组的最后合法下标2。",
    ),
    (
        "c-pointer",
        "p指向独占且有效的堆int，值为7；调用read_owned(p)。",
        "int read_owned(int*p){free(p);return *p;}",
        "int read_owned(int*p){int value=*p;free(p);return value;}",
        "释放p后读取*p，访问已结束生命周期的对象。",
    ),
    (
        "c-pointer",
        "调用make()后调用方读取返回指针；调用方不释放返回值。",
        "int*make(void){int x=7;return &x;}",
        "int*make(void){static int x=7;return &x;}",
        "局部自动对象x在函数返回时结束生命周期，返回指针被调用方解引用。",
    ),
    (
        "c-pointer",
        "p指向一个尚未释放的独占堆对象；调用dispose(p)。",
        "void dispose(int*p){free(p);free(p);}",
        "void dispose(int*p){free(p);}",
        "同一分配对象被free两次；第二次释放不是合法释放。",
    ),
    (
        "c-pointer",
        "调用read_value()。",
        "int read_value(void){int*p=NULL;return *p;}",
        "int read_value(void){int x=7;int*p=&x;return *p;}",
        "p为NULL时解引用。",
    ),
    (
        "array",
        "调用offset()。",
        "int offset(void){int a[2],b[2];return (int)(&b[0]-&a[0]);}",
        "int offset(void){int a[2];return (int)(&a[1]-&a[0]);}",
        "对两个不同数组的指针做减法，不满足同一数组内指针差的前提。",
    ),
    (
        "c-pointer",
        "调用dispose()；不假设malloc必定成功。",
        "void dispose(void){int x=7;free(&x);}",
        "void dispose(void){int*p=malloc(sizeof *p);if(p==NULL)return;*p=7;free(p);}",
        "把自动存储对象的地址传给free；它不是分配函数返回的指针。",
    ),
    (
        "c-pointer",
        "调用divide()。",
        "int divide(void){int d=0;return 7/d;}",
        "int divide(void){int d=1;return 7/d;}",
        "实际整数除数为0，执行整数除法发生未定义行为。",
    ),
    (
        "array",
        "调用alter()。",
        "int alter(void){char*p=\"abc\";p[0]='x';return p[0];}",
        "int alter(void){char p[]=\"abc\";p[0]='x';return p[0];}",
        "写入字符串字面量，数组对象不可按这种方式修改。",
    ),
    (
        "array",
        "调用set_values()；局部数组长度恰为2。",
        "void set_values(void){int a[2];for(int i=0;i<=2;i++)a[i]=i;}",
        "void set_values(void){int a[2];for(int i=0;i<2;i++)a[i]=i;}",
        "循环i=2时写a[2]，超出合法下标0、1。",
    ),
)

# node, source, actual return value, false return claim, concrete computation
FACTS = (
    (
        "array",
        (
            "int trace(void){int a[4]={1,3,5,7};int total=0;for(int "
            "i=0;i<4;i++)total+=a[i];return total;}"
        ),
        16,
        18,
        "1+3+5+7=16。",
    ),
    (
        "linked-list-traversal",
        (
            "struct N{int v;struct N*next;};int trace(void){struct N"
            " c={3,NULL},b={2,&c},a={1,&b};int count=0;for(struct N*"
            "p=&a;p!=NULL;p=p->next)count++;return count;}"
        ),
        3,
        2,
        "循环体分别处理a、b、c，count递增3次。",
    ),
    (
        "bubble-sort",
        (
            "int trace(void){int a[3]={3,1,2},swaps=0;for(int i=0;i<"
            "2;i++)if(a[i]>a[i+1]){int t=a[i];a[i]=a[i+1];a[i+1]=t;s"
            "waps++;}return swaps;}"
        ),
        2,
        1,
        "第一趟先交换3/1再交换3/2，共2次。",
    ),
    (
        "array",
        "int trace(void){int row=2,col=1,width=4;return row*width+col;}",
        9,
        8,
        "行列均从0开始，2*4+1=9。",
    ),
    (
        "circular-queue",
        "int trace(void){int cursor=4,capacity=6;cursor=(cursor+1)%capacity;return cursor;}",
        5,
        0,
        "只前进一步，(4+1)%6=5，不回绕到0。",
    ),
    (
        "binary-tree-traversal",
        (
            "struct N{struct N*l,*r;};int count(struct N*p){return p"
            "==NULL?0:1+count(p->l)+count(p->r);}int trace(void){str"
            "uct N a={NULL,NULL},b={NULL,NULL},root={&a,&b};return c"
            "ount(&root);}"
        ),
        3,
        5,
        "根和两个叶结点，共3个非空结点。",
    ),
    (
        "binary-heap",
        "int trace(void){int heap[3]={2,5,4};return heap[0];}",
        2,
        4,
        "给定数组下标0的值为2。",
    ),
    (
        "breadth-first-search",
        (
            "int trace(void){int edges[3][3]={{0,1,0},{0,0,1},{0,0,0"
            "}},d[3]={0,-1,-1},q[3]={0},head=0,tail=1;while(head<tai"
            "l){int u=q[head++];for(int v=0;v<3;v++)if(edges[u][v]&&"
            "d[v]<0){d[v]=d[u]+1;q[tail++]=v;}}return d[2];}"
        ),
        2,
        1,
        "只有0→1→2路径，从0到2的最少边数为2。",
    ),
    (
        "insertion-sort",
        (
            "int trace(void){int a[4]={2,4,6,0},j=2,moves=0;while(j>"
            "=0&&a[j]>5){a[j+1]=a[j];j--;moves++;}a[j+1]=5;return mo"
            "ves;}"
        ),
        1,
        2,
        "只搬移已有元素6一次；插入5自身的写入不计moves。",
    ),
    (
        "array-stack",
        "int trace(void){int a[4]={8,9,0,0},size=2;size--;return a[size];}",
        9,
        8,
        "本例size是元素数；递减后size=1，读取a[1]得到9。",
    ),
)


def draft(node, statement):
    return {
        "prerequisite_node_ids": [],
        "objectives": [{"id": "trace", "text": "按给定前提核对实际代码行为。"}],
        "terminology": [{"term": "state", "meaning": "当前例子明示的变量状态。"}],
        "conventions": {
            "index_base": 0,
            "capacity": None,
            "state_representation": statement,
            "not_applicable_reasons": ["不采用可变容量接口；数组边界由源代码的C声明确定。"],
        },
        "shared_example": {
            "input_description": statement,
            "initial_state": "按代码和明示前提初始化。",
            "steps": [
                {
                    "operation": "检查例子的一次调用。",
                    "expected_state": "核对所有可达路径。",
                    "expected_output": None,
                }
            ],
        },
        "reference_ids": ["GRAPH_REFERENCE_TO_BIND_AT_RUN_FREEZE"],
        "scenes": [
            {"role": r, "scene_key": r, "objective_ids": ["trace"], "depends_on": deps}
            for r, deps in [
                ("explanation", []),
                ("code", ["explanation"]),
                ("exercise", ["explanation", "code"]),
            ]
        ],
    }


def unit(node, source, statement):
    prefix = "#include <stddef.h>\n#include <stdlib.h>\n"
    contents = {
        "explanation": {"markdown": statement},
        "code": {
            "language": "C",
            "source": prefix + source,
            "expected_output": "函数不直接打印。",
            "key_steps": ["根据明确前提逐步核对函数执行。"],
            "display_only": True,
        },
        "exercise": {
            "items": [
                {
                    "id": f"q{i}",
                    "question": AUDIT_QUESTION,
                    "answer": "T",
                    "explanation": "不把计划中的预期直接当作已执行的事实。",
                }
                for i in range(1, 4)
            ]
        },
    }
    return {
        "node_id": node,
        "plan_draft": draft(node, statement),
        "resources": [
            {"resource_type": role, "prompt_version": "learning-resources-v1", "content": content}
            for role, content in contents.items()
        ],
    }


def benchmark_materials():
    materials = {"severe": [], "correct": [], "long": []}
    labels = []
    cases = []
    for node, pre, bad, good, counter in SAFETY:
        cases.append((node, bad, good, pre, pre, "code_safety", counter))
    for node, source, actual, false, counter in FACTS:
        prefix = "调用trace()；数组与下标从0开始，按源代码初始化。"
        cases.append(
            (
                node,
                source,
                source,
                prefix + f"本次返回值为{false}。",
                prefix + f"本次返回值为{actual}。",
                "fact",
                counter,
            )
        )
    for i, (node, bad, good, bad_claim, good_claim, category, counter) in enumerate(cases, 1):
        for kind, source, claim in [("severe", bad, bad_claim), ("correct", good, good_claim)]:
            id = f"new-{kind}-{i:02}"
            materials[kind].append({"id": id, "unit": unit(node, source, claim)})
            labels.append(
                {
                    "id": id,
                    "status": "ASSISTANT_PROPOSAL_PENDING_INDEPENDENT_HUMAN_REVIEW",
                    "expected_automatic_result": "reject_or_revise" if kind == "severe" else "pass",
                    "primary_category": category if kind == "severe" else None,
                    "concrete_condition_or_counterexample": counter
                    if kind == "severe"
                    else (
                        "对照使用修正后的真实代码/准确返回值，仍须人工独立核对；"
                        "不把此标签发送给模型。"
                    ),
                }
            )
    for i in range(10):
        # Long fixtures use actual correct example material, with bounded repeated audit context.
        value = deepcopy(materials["correct"][10 + i])
        value["id"] = f"new-long-{i + 1:02}"
        text = value["unit"]["resources"][0]["content"]["markdown"]
        text += "\n\n" + "\n".join(
            (
                f"核对段落{j + 1}：本例仅使用明示变量和前提；"
                "逐步跟踪代码，不推断未提供的输入，也不把预期当作执行证据。"
            )
            for j in range(100)
        )
        value["unit"]["resources"][0]["content"]["markdown"] = text
        materials["long"].append(value)
        labels.append(
            {
                "id": value["id"],
                "status": "ASSISTANT_PROPOSAL_PENDING_INDEPENDENT_HUMAN_REVIEW",
                "expected_automatic_result": "complete_schema_valid_and_pass",
                "primary_category": None,
                "concrete_condition_or_counterexample": "全文完整审核；重复段落不代表独立样本。",
            }
        )
    return materials, labels
