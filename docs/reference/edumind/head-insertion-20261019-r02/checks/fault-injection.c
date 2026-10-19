/* Test-only wrapper; candidate.c is included without changing its bytes. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int fail_at;
static int attempts;
static int allocated;
static int released;
static void *addresses[8];
static bool live[8];

static void *tracked_malloc(size_t size)
{
    ++attempts;
    if (attempts == fail_at) return NULL;
    void *address = malloc(size);
    assert(address != NULL);
    assert(allocated < 8);
    addresses[allocated] = address;
    live[allocated] = true;
    ++allocated;
    return address;
}

static void tracked_free(void *address)
{
    if (address == NULL) return;
    int slot = -1;
    for (int i = 0; i < allocated; ++i) {
        if (live[i] && addresses[i] == address) slot = i;
    }
    assert(slot >= 0); /* No unknown or already-freed allocation. */
    live[slot] = false;
    ++released;
    free(address);
}

#define malloc tracked_malloc
#define free tracked_free
#define main generated_main
#include "../candidate.c"
#undef main
#undef free
#undef malloc

static void check_contract(void)
{
    Node *head = NULL;
    int successful[3];
    int count = 0;
    for (int value = 1; value <= 3; ++value) {
        Node *old_head = head;
        head = insert_head(head, value); /* Same caller assignment as generated main. */
        if (value == fail_at) {
            assert(head == old_head); /* Failed insert preserves caller ownership. */
        } else {
            assert(head != NULL && head != old_head);
            assert(head->data == value && head->next == old_head);
            successful[count++] = value;
        }
        Node *p = head;
        for (int i = count - 1; i >= 0; --i) {
            assert(p != NULL && p->data == successful[i]);
            p = p->next;
        }
        assert(p == NULL); /* Also detects cycles / extra nodes in this finite example. */
        assert(allocated - released == count);
    }
    free_list(head);
    /* head is passed by value; do not read its dangling value. Reset in the caller. */
    head = NULL;
    assert(head == NULL);
}

int main(int argc, char **argv)
{
    assert(argc == 3);
    fail_at = atoi(argv[2]);
    assert(fail_at >= 0 && fail_at <= 3);
    if (strcmp(argv[1], "program") == 0) {
        assert(generated_main() == 0);
    } else {
        assert(strcmp(argv[1], "contract") == 0);
        check_contract();
    }
    assert(attempts == 3);
    assert(allocated == (fail_at == 0 ? 3 : 2));
    assert(released == allocated);
    for (int i = 0; i < allocated; ++i) assert(!live[i]);
    fprintf(stderr, "PASS mode=%s fail_at=%d attempts=%d allocated=%d freed=%d live=0\n",
            argv[1], fail_at, attempts, allocated, released);
    return 0;
}
