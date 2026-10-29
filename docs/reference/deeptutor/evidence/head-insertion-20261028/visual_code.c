#include <stdlib.h>
typedef struct Node { int data; struct Node *next; } Node;
Node *push_front(Node **head, int value) {
    Node *p = malloc(sizeof *p);
    if (p == NULL) return 0;
    p->value = value;
    p->next = *head;
    *head = p;
}
