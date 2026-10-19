int main(void) {
  Node *head = NULL;
  head = insertHead(head, 1);
  head = insertHead(head, 2);
  head = insertHead(head, 3);
  printList(head);
  freeList(&head);
  return 0;
}
