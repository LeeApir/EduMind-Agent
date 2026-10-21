#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

// Test fixture only. The original course omits this alias; its full program
// is compiled separately and fails. This binding isolates the function bodies.
typedef struct Node Node;
static int fail_at;
static int calls;
static int allocated;
static int released;
static int live;
static void *tracked[16];

static void report(void) {
    fprintf(stderr, "TRACK calls=%d allocated=%d released=%d live=%d\n",
            calls, allocated, released, live);
}

static void *tracked_malloc(size_t size) {
    ++calls;
    if (calls == fail_at) {
        fprintf(stderr, "INJECT malloc_failure_at=%d prior_live=%d\n", calls, live);
        return NULL;
    }
    void *p = malloc(size);
    assert(p != NULL);
    assert(allocated < 16);
    tracked[allocated++] = p;
    ++live;
    return p;
}

static void tracked_free(void *p) {
    if (p == NULL) return;
    int found = 0;
    for (int i = 0; i < allocated; ++i) {
        if (tracked[i] == p) {
            tracked[i] = NULL;
            found = 1;
            break;
        }
    }
    assert(found && "unknown pointer or double free");
    ++released;
    --live;
    free(p);
}

// Macro hooks change allocator observation, not the original function bodies.
#define malloc tracked_malloc
#include "head-functions.c"
#undef malloc
#define free tracked_free
#include "print-function.c"
#include "free-function.c"
#undef free

int main(int argc, char **argv) {
    fail_at = argc > 1 ? atoi(argv[1]) : 0;
    atexit(report);
    Node *head = NULL;
    // Calls obey the ORIGINAL declared Node ** contract. The course main does
    // not obey it; this test driver must not be presented as the original main.
    for (int i = 1; i <= 3; ++i) insertHead(&head, i);
    Node *p = head;
    for (int expected = 3; expected >= 1; --expected) {
        assert(p != NULL && p->data == expected);
        p = p->next;
    }
    assert(p == NULL);
    printList(head);
    freeList(&head);
    assert(head == NULL && allocated == 3 && released == 3 && live == 0);
    freeList(&head);
    assert(head == NULL && released == 3 && live == 0);
    return 0;
}
