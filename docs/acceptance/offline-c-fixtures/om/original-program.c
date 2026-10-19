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

void printList(Node *head) {
  Node *p = head;
  while (p != NULL) {
    printf("%d -> ", p->data);
    p = p->next;
  }
  printf("NULL\n");
}

void freeList(Node **head) {
  Node *p = *head, *next;
  while (p != NULL) {
    next = p->next;
    free(p);
    p = next;
  }
  *head = NULL;
}

int main(void) {
  Node *head = NULL;
  head = insertHead(head, 1);
  head = insertHead(head, 2);
  head = insertHead(head, 3);
  printList(head);
  freeList(&head);
  return 0;
}
