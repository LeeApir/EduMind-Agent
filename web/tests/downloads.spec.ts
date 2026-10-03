import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NotesDownload from "../src/components/NotesDownload.vue";
import { downloadFile } from "../src/api/downloads";

const stubs = {
  NButton: {
    props: ["disabled"], emits: ["click"],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
};

describe("reviewed file downloads", () => {
  beforeEach(() => {
    Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => "blob:download"), configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    vi.spyOn(window, "setTimeout").mockImplementation((callback) => { (callback as TimerHandler & (() => void))(); return 1; });
  });
  afterEach(() => vi.restoreAllMocks());

  it("downloads server bytes with its safe filename and does not POST", async () => {
    const payload = "# 已审核讲解\n";
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(payload, {
      headers: { "Content-Disposition": 'attachment; filename="learning-notes-unit-1.md"' },
    }));
    await downloadFile("/api/learning-units/unit-1/notes.md", "fallback.md", () => true, fetchImpl);
    expect(fetchImpl).toHaveBeenCalledWith("/api/learning-units/unit-1/notes.md", { credentials: "same-origin" });
    expect(vi.mocked(URL.createObjectURL).mock.calls[0][0]).toBeInstanceOf(Blob);
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:download");
  });

  it("rejects unsafe filenames and stale selected versions", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response("data", {
      headers: { "Content-Disposition": 'attachment; filename="../unsafe.md"' },
    }));
    await downloadFile("/notes", "safe.md", () => false, fetchImpl);
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled();
    await downloadFile("/notes", "safe.md", () => true, fetchImpl);
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
  });

  it("keeps history disabled and retries a failed current notes download", async () => {
    const fetchImpl = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response("missing", { status: 404 }))
      .mockResolvedValueOnce(new Response("# 当前正式讲解", {
        headers: { "Content-Disposition": 'attachment; filename="learning-notes-unit-1.md"' },
      }));
    vi.stubGlobal("fetch", fetchImpl);
    const wrapper = mount(NotesDownload, { props: { unitId: "unit-1", current: false }, global: { stubs } });
    expect(wrapper.get('[data-testid="download-notes"]').attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("历史场景");
    await wrapper.setProps({ current: true });
    await wrapper.get('[data-testid="download-notes"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("重试下载");
    await wrapper.get('[data-testid="download-notes"]').trigger("click");
    await flushPromises();
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
    wrapper.unmount();
    vi.unstubAllGlobals();
  });
});
