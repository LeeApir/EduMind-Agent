/* Reviewed fixed-domain driver; original source bytes are included unchanged. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int fail_at, attempts, allocated, released;
static bool contract_mode, freeing;
static void *slots[8];
static bool live[8];
static void *latest;
static int emitted_step;
static void *tracked_malloc(size_t size);
static void tracked_free(void *address);
#define malloc tracked_malloc
#define free tracked_free
#define main generated_main
#ifndef SOURCE_C
#define SOURCE_C "candidate.c"
#endif
#include SOURCE_C
#undef main
#undef free
#undef malloc

static void snapshot(Node *head, int step, const char *basis)
{
    int values[3], count = 0;
    Node *p = head;
    while (p != NULL && count < 3) {
        values[count++] = p->data;
        p = p->next;
    }
    assert(p == NULL);
    int expected = 0;
    for (int n = step; n >= 1; --n) {
        if (n != fail_at) {
            assert(expected < count && values[expected] == n);
            ++expected;
        }
    }
    assert(count == expected && count == allocated - released);
    fprintf(stderr, "EVENT {\"event\":\"insert_state\",\"step\":%d,\"basis\":\"%s\",\"values\":[", step, basis);
    for (int i = 0; i < count; ++i) fprintf(stderr, "%s%d", i ? "," : "", values[i]);
    fprintf(stderr, "],\"count\":%d}\n", count);
    emitted_step = step;
}

static void *tracked_malloc(size_t size)
{
    if (!contract_mode && attempts > emitted_step) snapshot(latest, attempts, "allocation_root_before_next_attempt");
    ++attempts;
    fprintf(stderr, "EVENT {\"event\":\"attempt\",\"step\":%d,\"injected\":%s,\"prior_live\":%d}\n", attempts, attempts == fail_at ? "true" : "false", allocated-released);
    if (attempts == fail_at) return NULL;
    void *address = malloc(size);
    assert(address != NULL && allocated < 8);
    slots[allocated] = address;
    live[allocated] = true;
    fprintf(stderr, "EVENT {\"event\":\"allocate\",\"slot\":%d}\n", allocated);
    ++allocated;
    latest = address;
    return address;
}

static void tracked_free(void *address)
{
    if (address == NULL) return;
    if (!contract_mode && !freeing && attempts > emitted_step) snapshot(latest, attempts, "allocation_root_before_first_free");
    freeing = true;
    int slot = -1;
    for (int i = 0; i < allocated; ++i) if (live[i] && slots[i] == address) slot = i;
    assert(slot >= 0 && "unknown or repeated release");
    live[slot] = false;
    ++released;
    fprintf(stderr, "EVENT {\"event\":\"free\",\"slot\":%d}\n", slot);
    free(address);
}

static void contract(void)
{
    Node *head = NULL;
    for (int value = 1; value <= 3; ++value) {
        Node *old_head = head;
        head = insert_head(head, value);
        if (value == fail_at) assert(head == old_head);
        else assert(head != NULL && head != old_head && head->data == value && head->next == old_head);
        snapshot(head, value, "caller_head_after_assignment");
    }
    print_list(head);
    free_list(head);
    head = NULL; /* Explicit caller reset: not a property of free_list(Node*). */
    free_list(head);
    assert(head == NULL);
}

int main(int argc, char **argv)
{
    assert(argc == 3);
    contract_mode = strcmp(argv[1], "contract") == 0;
    assert(contract_mode || strcmp(argv[1], "program") == 0);
    fail_at = atoi(argv[2]);
    assert(fail_at >= 0 && fail_at <= 3);
    if (contract_mode) contract();
    else assert(generated_main() == 0);
    assert(attempts == 3 && emitted_step == 3);
    assert(allocated == (fail_at == 0 ? 3 : 2) && released == allocated);
    for (int i = 0; i < allocated; ++i) assert(!live[i]);
    fprintf(stderr, "EVENT {\"event\":\"summary\",\"attempts\":%d,\"allocated\":%d,\"released\":%d,\"live\":0,\"caller_reset\":%s,\"reset_by\":\"%s\"}\n", attempts, allocated, released, contract_mode ? "true" : "null", contract_mode ? "driver_caller" : "not_observable_after_main");
    return 0;
}
