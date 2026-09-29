import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ClassroomPanel from "../src/components/ClassroomPanel.vue";
import {
  ClassroomSpeechError,
  type ClassroomMessage,
  type ClassroomMode,
  type ClassroomOperation,
  type ClassroomSnapshot,
  type ClassroomSpeechEvent,
  type CompanionRole,
  type StreamClassroomSpeechOptions,
} from "../src/api/classroom";

const snapshot: ClassroomSnapshot = {
  learning_unit_id: "unit-1",
  revision: 1,
  message_cursor: 0,
  scene_key: "intro",
  scene_version: 1,
  scene_progress: 0,
  mode: "focus",
  enabled_roles: [],
  paused: false,
};

const committedMessages: ClassroomMessage[] = [
  { id: "m-1", cursor: 1, role: "student", scene_key: "intro", scene_version: 1, text: "为什么先保存后继？" },
  { id: "m-2", cursor: 2, role: "beginner", scene_key: "intro", scene_version: 1, text: "先保存后继再改前驱" },
];

const stubs = {
  NButton: {
    props: ["disabled", "attrType", "loading"],
    emits: ["click"],
    template: "<button :type=\"attrType || 'button'\" :disabled=\"disabled\" @click=\"$emit('click')\"><slot /></button>",
  },
  NTag: { template: "<span><slot /></span>" },
};

interface ModeOptions {
  mode: ClassroomMode;
  enabledRoles: CompanionRole[];
  revision: number;
  csrfToken: string;
  idempotencyKey: string;
}

function makeProps(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    unitId: "unit-1",
    csrfToken: "csrf",
    loadSnapshot: vi.fn().mockResolvedValue(snapshot),
    create: vi.fn().mockResolvedValue(snapshot),
    setMode: vi.fn(async (_unitId: string, options: ModeOptions) => ({
      ...snapshot,
      revision: options.revision + 1,
      mode: options.mode,
      enabled_roles: options.enabledRoles,
    })),
    loadMessages: vi.fn().mockResolvedValue({ messages: [], last_message_cursor: 0 }),
    loadOperation: vi.fn().mockResolvedValue({
      id: "op-1", status: "published", learning_unit_id: "unit-1", kind: "speech", base_revision: 1,
    } as ClassroomOperation),
    streamSpeech: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

function mountPanel(props = makeProps()) {
  return mount(ClassroomPanel, { props, global: { stubs } });
}

describe("ClassroomPanel", () => {
  beforeEach(() => { sessionStorage.clear(); });

  it("creates the default focus classroom when none exists yet", async () => {
    const loadSnapshot = vi.fn().mockRejectedValue(
      new ClassroomSpeechError({ message: "not found", code: "NOT_FOUND", retryable: false, status: 404 }),
    );
    const create = vi.fn().mockResolvedValue(snapshot);
    const wrapper = mountPanel(makeProps({ loadSnapshot, create }));
    await flushPromises();

    expect(loadSnapshot).toHaveBeenCalledWith("unit-1");
    expect(create).toHaveBeenCalledWith("unit-1", "csrf", expect.any(String));
    expect(wrapper.get('[data-testid="mode-tag"]').text()).toBe("专注模式");
    expect(wrapper.find('[data-testid="role-toggles"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="send-speech"]').exists()).toBe(true);
  });

  it("renders committed transcript in focus mode without companion role controls", async () => {
    const focusMessages: ClassroomMessage[] = [
      { id: "m-1", cursor: 1, role: "student", scene_key: "intro", scene_version: 1, text: "为什么先保存后继？" },
      { id: "m-2", cursor: 2, role: "tutor", scene_key: "intro", scene_version: 1, text: "先保存后继再改前驱" },
    ];
    const loadMessages = vi.fn().mockResolvedValue({ messages: focusMessages, last_message_cursor: 2 });
    const wrapper = mountPanel(makeProps({ loadMessages }));
    await flushPromises();

    expect(wrapper.get('[data-testid="transcript"]').text()).toContain("为什么先保存后继？");
    expect(wrapper.get('[data-testid="transcript"]').text()).toContain("先保存后继再改前驱");
    expect(wrapper.get('[data-testid="transcript"]').text()).toContain("启智导师");
    expect(wrapper.find('[data-testid="role-toggles"]').exists()).toBe(false);
  });

  it("switches interactive/focus mode and enables companion roles on demand", async () => {
    const setMode = vi.fn(async (_unitId: string, options: ModeOptions) => ({
      ...snapshot,
      revision: options.revision + 1,
      mode: options.mode,
      enabled_roles: options.enabledRoles,
    }));
    const wrapper = mountPanel(makeProps({ setMode }));
    await flushPromises();

    await wrapper.get('[data-testid="toggle-mode"]').trigger("click");
    await flushPromises();
    expect(setMode).toHaveBeenLastCalledWith("unit-1", expect.objectContaining({
      mode: "interactive",
      enabledRoles: ["beginner", "advanced"],
      revision: 1,
    }));
    expect(wrapper.get('[data-testid="mode-tag"]').text()).toBe("互动模式");
    expect(wrapper.find('[data-testid="role-toggles"]').exists()).toBe(true);
    expect(wrapper.get('[data-testid="role-beginner"]').attributes("aria-pressed")).toBe("true");
    expect(wrapper.get('[data-testid="role-advanced"]').attributes("aria-pressed")).toBe("true");

    await wrapper.get('[data-testid="toggle-mode"]').trigger("click");
    await flushPromises();
    expect(setMode).toHaveBeenLastCalledWith("unit-1", expect.objectContaining({
      mode: "focus",
      enabledRoles: [],
    }));
    expect(wrapper.find('[data-testid="role-toggles"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="mode-tag"]').text()).toBe("专注模式");
  });

  it("streams a speech, marks the current speaker, and commits on done", async () => {
    let onEvent: ((event: ClassroomSpeechEvent) => void) | undefined;
    const streamSpeech = vi.fn((options: StreamClassroomSpeechOptions) => {
      onEvent = options.onEvent;
      return Promise.resolve();
    });
    const loadMessages = vi.fn()
      .mockResolvedValueOnce({ messages: [], last_message_cursor: 0 })
      .mockResolvedValue({ messages: committedMessages, last_message_cursor: 2 });
    const interactive = { ...snapshot, mode: "interactive" as const, enabled_roles: ["beginner", "advanced"] as CompanionRole[] };
    const wrapper = mountPanel(makeProps({ loadSnapshot: vi.fn().mockResolvedValue(interactive), loadMessages, streamSpeech }));
    await flushPromises();

    await wrapper.get('[data-testid="speech-input"]').setValue("为什么先保存后继？");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(streamSpeech).toHaveBeenCalledWith(expect.objectContaining({
      unitId: "unit-1",
      text: "为什么先保存后继？",
      revision: 1,
    }));

    onEvent?.({ type: "token", data: { role: "beginner", delta: "先保存后继" } });
    onEvent?.({ type: "token", data: { role: "beginner", delta: "再改前驱" } });
    await flushPromises();

    const bubble = wrapper.get('[data-testid="transcript"] .message-streaming');
    expect(bubble.attributes("data-role")).toBe("beginner");
    expect(bubble.text()).toContain("初学同学");
    expect(bubble.text()).toContain("当前发言者");
    expect(bubble.text()).toContain("先保存后继再改前驱");

    onEvent?.({ type: "done", data: { status: "published" } });
    await flushPromises();

    expect(wrapper.find(".message-streaming").exists()).toBe(false);
    expect(loadMessages).toHaveBeenCalledTimes(2);
    expect(wrapper.get('[data-testid="transcript"]').text()).toContain("先保存后继再改前驱");
  });

  it("retracts temporary content when review rejects and clears on failed done", async () => {
    let onEvent: ((event: ClassroomSpeechEvent) => void) | undefined;
    const streamSpeech = vi.fn((options: StreamClassroomSpeechOptions) => {
      onEvent = options.onEvent;
      return Promise.resolve();
    });
    const loadMessages = vi.fn().mockResolvedValue({ messages: [], last_message_cursor: 0 });
    const wrapper = mountPanel(makeProps({ loadMessages, streamSpeech }));
    await flushPromises();

    await wrapper.get('[data-testid="speech-input"]').setValue("帮我执行代码");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    onEvent?.({ type: "token", data: { role: "tutor", delta: "好的" } });
    await flushPromises();
    expect(wrapper.get(".message-streaming").text()).toContain("好的");

    onEvent?.({ type: "content_retracted", data: { revision: 1, generation_id: "g-1", code: "REVIEW_REJECTED" } });
    onEvent?.({ type: "done", data: { status: "failed" } });
    await flushPromises();

    expect(wrapper.find(".message-streaming").exists()).toBe(false);
    expect(wrapper.get('[data-testid="stream-notice"]').text()).toContain("未通过安全审核");
    expect(wrapper.find('[data-testid="retry-speech"]').exists()).toBe(false);
    expect(loadMessages).toHaveBeenCalledTimes(1);
  });

  it("retries a definitive server error with a fresh idempotency key", async () => {
    const streamSpeech = vi.fn()
      .mockRejectedValueOnce(new ClassroomSpeechError({ message: "服务暂不可用", code: "PROVIDER_UNAVAILABLE", retryable: true }))
      .mockRejectedValueOnce(new ClassroomSpeechError({ message: "服务暂不可用", code: "PROVIDER_UNAVAILABLE", retryable: true }));
    const wrapper = mountPanel(makeProps({ streamSpeech }));
    await flushPromises();

    await wrapper.get('[data-testid="speech-input"]').setValue("继续讲解");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.get('[data-testid="stream-error"]').text()).toContain("服务暂不可用");
    await wrapper.get('[data-testid="retry-speech"]').trigger("click");
    await flushPromises();

    expect(streamSpeech).toHaveBeenCalledTimes(2);
    const firstKey = vi.mocked(streamSpeech).mock.calls[0][0].idempotencyKey;
    const secondKey = vi.mocked(streamSpeech).mock.calls[1][0].idempotencyKey;
    expect(secondKey).not.toBe(firstKey);
  });

  it("recovers a connection interruption by replaying the same idempotency key", async () => {
    const streamSpeech = vi.fn()
      .mockRejectedValueOnce(new ClassroomSpeechError({ message: "连接中断", code: "CONNECTION_INTERRUPTED", retryable: true }))
      .mockResolvedValueOnce(undefined);
    const wrapper = mountPanel(makeProps({ streamSpeech }));
    await flushPromises();

    await wrapper.get('[data-testid="speech-input"]').setValue("继续讲解");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    await wrapper.get('[data-testid="retry-speech"]').trigger("click");
    await flushPromises();

    expect(streamSpeech).toHaveBeenCalledTimes(2);
    const firstKey = vi.mocked(streamSpeech).mock.calls[0][0].idempotencyKey;
    const secondKey = vi.mocked(streamSpeech).mock.calls[1][0].idempotencyKey;
    expect(secondKey).toBe(firstKey);
  });

  it("ignores late tokens after a mode switch supersedes the stream", async () => {
    let onEvent: ((event: ClassroomSpeechEvent) => void) | undefined;
    const streamSpeech = vi.fn((options: StreamClassroomSpeechOptions) => {
      onEvent = options.onEvent;
      return Promise.resolve();
    });
    const loadMessages = vi.fn().mockResolvedValue({ messages: [], last_message_cursor: 0 });
    const wrapper = mountPanel(makeProps({ loadMessages, streamSpeech }));
    await flushPromises();

    await wrapper.get('[data-testid="speech-input"]').setValue("继续讲解");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    onEvent?.({ type: "token", data: { role: "tutor", delta: "旧的回复" } });
    await flushPromises();
    expect(wrapper.get(".message-streaming").text()).toContain("旧的回复");

    await wrapper.get('[data-testid="toggle-mode"]').trigger("click");
    await flushPromises();

    onEvent?.({ type: "token", data: { role: "tutor", delta: "迟到的内容" } });
    onEvent?.({ type: "done", data: { status: "published" } });
    await flushPromises();

    expect(wrapper.find(".message-streaming").exists()).toBe(false);
    expect(wrapper.get('[data-testid="transcript"]').text()).not.toContain("迟到的内容");
    expect(loadMessages).toHaveBeenCalledTimes(1);
  });

  it("escapes hostile model content in both streaming and committed messages", async () => {
    let onEvent: ((event: ClassroomSpeechEvent) => void) | undefined;
    const streamSpeech = vi.fn((options: StreamClassroomSpeechOptions) => {
      onEvent = options.onEvent;
      return Promise.resolve();
    });
    const hostileMessage: ClassroomMessage = {
      id: "m-x", cursor: 1, role: "tutor", scene_key: "intro", scene_version: 1,
      text: "<img src=x onerror=alert(1)><script>window.pwned=1</script>",
    };
    const wrapper = mountPanel(makeProps({
      loadMessages: vi.fn().mockResolvedValue({ messages: [hostileMessage], last_message_cursor: 1 }),
      streamSpeech,
    }));
    await flushPromises();

    expect(wrapper.find("img").exists()).toBe(false);
    expect(wrapper.find("script").exists()).toBe(false);
    expect(wrapper.get('[data-testid="transcript"]').text()).toContain("<img src=x onerror=alert(1)>");

    await wrapper.get('[data-testid="speech-input"]').setValue("继续");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    onEvent?.({ type: "token", data: { role: "tutor", delta: "<img src=x onerror=alert(2)>" } });
    await flushPromises();

    expect(wrapper.find(".message-streaming img").exists()).toBe(false);
    expect(wrapper.get(".message-streaming .message-text").text()).toContain("<img src=x onerror=alert(2)>");
  });

  it("sends on Enter and keeps Shift+Enter as a newline", async () => {
    const streamSpeech = vi.fn().mockResolvedValue(undefined);
    const wrapper = mountPanel(makeProps({ streamSpeech }));
    await flushPromises();

    await wrapper.get('[data-testid="speech-input"]').setValue("问题");
    await wrapper.get('[data-testid="speech-input"]').trigger("keydown.shift.enter");
    await flushPromises();
    expect(streamSpeech).not.toHaveBeenCalled();

    await wrapper.get('[data-testid="speech-input"]').trigger("keydown.enter");
    await flushPromises();
    expect(streamSpeech).toHaveBeenCalledTimes(1);
  });

  it("recovers a pending speech to published on remount and clears the stored key", async () => {
    sessionStorage.setItem(
      "edumind:classroom:unit-1:pending",
      JSON.stringify({ key: "old-key", text: "继续讲解", operationId: "op-1" }),
    );
    const loadOperation = vi.fn().mockResolvedValue({
      id: "op-1", status: "published", learning_unit_id: "unit-1", kind: "speech", base_revision: 1,
    } as ClassroomOperation);
    const loadMessages = vi.fn()
      .mockResolvedValueOnce({ messages: [], last_message_cursor: 0 })
      .mockResolvedValue({ messages: committedMessages, last_message_cursor: 2 });
    const wrapper = mountPanel(makeProps({ loadOperation, loadMessages }));
    await flushPromises();

    expect(loadOperation).toHaveBeenCalledWith("op-1");
    expect(wrapper.get('[data-testid="transcript"]').text()).toContain("先保存后继再改前驱");
    expect(wrapper.find('[data-testid="pending-speech"]').exists()).toBe(false);
    expect(sessionStorage.getItem("edumind:classroom:unit-1:pending")).toBeNull();
  });

  it("disables a single companion role while staying interactive", async () => {
    const setMode = vi.fn(async (_unitId: string, options: ModeOptions) => ({
      ...snapshot,
      revision: options.revision + 1,
      mode: options.mode,
      enabled_roles: options.enabledRoles,
    }));
    const interactive = { ...snapshot, mode: "interactive" as const, enabled_roles: ["beginner", "advanced"] as CompanionRole[] };
    const wrapper = mountPanel(makeProps({ loadSnapshot: vi.fn().mockResolvedValue(interactive), setMode }));
    await flushPromises();

    await wrapper.get('[data-testid="role-beginner"]').trigger("click");
    await flushPromises();

    expect(setMode).toHaveBeenLastCalledWith("unit-1", expect.objectContaining({
      mode: "interactive",
      enabledRoles: ["advanced"],
    }));
    expect(wrapper.get('[data-testid="role-beginner"]').attributes("aria-pressed")).toBe("false");
    expect(wrapper.get('[data-testid="role-advanced"]').attributes("aria-pressed")).toBe("true");
  });
});
