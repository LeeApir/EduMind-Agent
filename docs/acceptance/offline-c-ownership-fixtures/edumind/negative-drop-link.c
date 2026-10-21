#include <stdio.h>
#include <stdlib.h>

/* 节点：数据域 data + 指针域 next */
typedef struct Node {
    int data;
    struct Node *next;
} Node;

/* 头插法：把 data 放入新节点，插到链表最前端，返回新的头指针 */
Node *insert_head(Node *head, int data)
{
    Node *new_node = (Node *)malloc(sizeof(Node));
    if (new_node == NULL) {
        return head; /* 分配失败，保持原链表不变 */
    }
    new_node->data = data;
    new_node->next = NULL; /* 第一步：新节点接到原链表前面 */
    head = new_node;       /* 第二步：头指针改指向新节点 */
    return head;
}

/* 遍历：从 head 出发沿 next 依次打印，直到 NULL */
void print_list(Node *head)
{
    Node *p = head;
    while (p != NULL) {
        printf("%d ", p->data);
        p = p->next;
    }
    printf("\n");
}

/* 释放：先保存 next，再 free 当前节点，最后 head 置为 NULL */
void free_list(Node *head)
{
    Node *p = head;
    while (p != NULL) {
        Node *next = p->next;
        free(p);
        p = next;
    }
}

int main(void)
{
    Node *head = NULL; /* 空链表：head -> NULL */

    head = insert_head(head, 1); /* head -> [1] -> NULL */
    head = insert_head(head, 2); /* head -> [2] -> [1] -> NULL */
    head = insert_head(head, 3); /* head -> [3] -> [2] -> [1] -> NULL */

    print_list(head); /* 输出：3 2 1 */

    free_list(head);
    head = NULL; /* 释放后置空，避免悬空指针 */

    return 0;
}