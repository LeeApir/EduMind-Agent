void printList(Node *head) {
  Node *p = head;
  while (p != NULL) {
    printf("%d -> ", p->data);
    p = p->next;
  }
  printf("NULL\n");
}
