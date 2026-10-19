#include <stdio.h>
#include <stdlib.h>
struct Node { int data; struct Node *next; }; /* ① 结构 */
 
struct Node* createNode(int value) { /* ② 建节点 */
    struct Node *n = malloc(sizeof(struct Node));
    if (n == NULL) return NULL;
    n->data = value;  n->next = NULL;
    return n;
}
 
void insertHead(struct Node **head, int value) { /* ③ 头插 */
    struct Node *n = createNode(value);
    n->next = *head;  /* ① 先接上 */
    *head = n;        /* ② 再改 head */
}
