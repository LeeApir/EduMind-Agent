void freeList(Node **head) {
  Node *p = *head, *next;
  while (p != NULL) {
    next = p->next;
    free(p);
    p = next;
  }
  *head = NULL;
}
