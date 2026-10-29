#include <stdio.h>
#include <stdlib.h>
typedef struct Node {
    int data;
    struct Node *next;
} Node;
int push_front(Node **head, int value)
{
    Node *new_node = malloc(sizeof *new_node);
    if (new_node == NULL) {
        return 0;
    }
    new_node->data = value;
    new_node->next = *head;
    *head = new_node;
    return 1;
}
void free_list(Node *head)
{
    while (head != NULL) {
        Node *next = head->next;
        free(head);
        head = next;
    }
}
void print_list(const Node *head)
{
    for (const Node *current = head; current != NULL; current = current->next) {
        printf("%d", current->data);
        if (current->next != NULL) {
            printf(" -> ");
        }
    }
    printf(" -> NULL\n");
}
int main(void)
{
    Node *head = NULL;
    const int values[] = {4, 7, 9};
    for (size_t i = 0; i < sizeof values / sizeof values[0]; ++i) {
        if (!push_front(&head, values[i])) {
            fprintf(stderr, "Memory allocation failed.\n");
            free_list(head);
            return EXIT_FAILURE;
        }
        print_list(head);
    }
    free_list(head);
    return EXIT_SUCCESS;
}
