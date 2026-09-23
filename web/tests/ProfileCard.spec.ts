import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import ProfileCard from "../src/components/ProfileCard.vue";
import { ProfileRequestError, type Profile } from "../src/api/profile";

const stubs = {
  NButton: { emits: ["click"], template: "<button @click=\"$emit('click')\"><slot /></button>" },
  NTag: { template: "<span><slot /></span>" },
  NInput: {
    props: ["value"],
    emits: ["update:value"],
    template: "<textarea @input=\"$emit('update:value', $event.target.value)\" />",
  },
};

function makeProfile(overrides: Partial<Profile> = {}): Profile {
  return {
    id: "profile-1",
    version: 1,
    initial_query: "想理解链表",
    professional_background: null,
    knowledge_base: null,
    cognitive_style: null,
    learning_goals: null,
    error_preferences: null,
    engineering_preference: null,
    extended_dimensions: null,
    evidence: {},
    updated_at: "2026-09-23T00:00:00+00:00",
    ...overrides,
  };
}

const sampleProfile = makeProfile({
  version: 3,
  professional_background: { major: "计算机" },
  cognitive_style: { pace: "steady" },
  learning_goals: { goal: "掌握指针" },
  error_preferences: ["边界条件"],
  evidence: {
    professional_background: [{
      source: "learner_statement",
      confidence: 0.9,
      observed_at: "2026-09-23T00:00:00+00:00",
      profile_version: 1,
    }],
    cognitive_style: [{
      source: "learning_behavior",
      confidence: 0.7,
      observed_at: "2026-09-23T00:00:00+00:00",
      profile_version: 2,
    }],
    learning_goals: [{
      source: "manual_correction",
      confidence: 1.0,
      observed_at: "2026-09-23T00:00:00+00:00",
      profile_version: 3,
    }],
    error_preferences: [{
      source: "explicit_feedback",
      confidence: 0.8,
      observed_at: "2026-09-23T00:00:00+00:00",
      profile_version: 2,
    }],
  },
});

function mountCard(overrides: {
  fetchProfile?: () => Promise<Profile>;
  correctProfile?: () => Promise<Profile>;
  ensureSession?: () => Promise<string>;
} = {}) {
  const fetchProfile = overrides.fetchProfile ?? vi.fn().mockResolvedValue(sampleProfile);
  const correctProfile = overrides.correctProfile ?? vi.fn();
  const ensureSession = overrides.ensureSession ?? vi.fn().mockResolvedValue("c".repeat(64));
  const wrapper = mount(ProfileCard, {
    props: { fetchProfile, correctProfile, ensureSession },
    global: { stubs },
  });
  return { wrapper, fetchProfile, correctProfile, ensureSession };
}

describe("ProfileCard", () => {
  it("classifies each field and never renders raw evidence", async () => {
    const { wrapper } = mountCard();
    await flushPromises();

    expect(wrapper.get('[data-testid="profile-field-knowledge_base"]').text()).toContain("未知");
    expect(wrapper.get('[data-testid="profile-field-professional_background"]').text()).toContain("已知");
    expect(wrapper.get('[data-testid="profile-field-cognitive_style"]').text()).toContain("推断");
    expect(wrapper.get('[data-testid="profile-field-learning_goals"]').text()).toContain("用户修正");
    expect(wrapper.get('[data-testid="profile-initial-query"]').text()).toContain("想理解链表");
    expect(wrapper.text()).toContain("版本 v3");
    expect(wrapper.text()).not.toContain("confidence");
    expect(wrapper.text()).not.toContain("observed_at");
    expect(wrapper.text()).not.toContain("manual_correction");
  });

  it("shows an empty state when no profile exists yet", async () => {
    const { wrapper } = mountCard({
      fetchProfile: vi.fn().mockRejectedValue(
        new ProfileRequestError({ message: "还没有生成学习画像。", code: "NOT_FOUND", retryable: false }),
      ),
    });
    await flushPromises();

    expect(wrapper.get('[data-testid="profile-empty"]').text()).toContain("还没有生成画像");
  });

  it("shows a load error and retries", async () => {
    const fetchProfile = vi.fn()
      .mockRejectedValueOnce(new ProfileRequestError({ message: "网络中断", code: "CONNECTION_FAILED" }))
      .mockResolvedValueOnce(sampleProfile);
    const { wrapper } = mountCard({ fetchProfile });
    await flushPromises();

    expect(wrapper.get('[data-testid="profile-load-error"]').text()).toContain("网络中断");
    await wrapper.get('[data-testid="profile-load-error"] button').trigger("click");
    await flushPromises();

    expect(fetchProfile).toHaveBeenCalledTimes(2);
    expect(wrapper.get('[data-testid="profile-card"]').text()).toContain("学习目标");
  });

  it("does not offer editing for non-editable dimensions", async () => {
    const { wrapper } = mountCard();
    await flushPromises();

    expect(wrapper.find('[data-testid="profile-field-knowledge_base"] button').exists()).toBe(false);
    expect(wrapper.find('[data-testid="profile-field-cognitive_style"] button').exists()).toBe(false);
    expect(wrapper.find('[data-testid="profile-field-learning_goals"] button').exists()).toBe(true);
  });

  it("saves a whitelisted correction and shows the updated version", async () => {
    const updated = makeProfile({
      version: 4,
      learning_goals: { goal: "掌握指针" },
      evidence: {
        learning_goals: [{
          source: "manual_correction",
          confidence: 1.0,
          observed_at: "2026-09-23T01:00:00+00:00",
          profile_version: 4,
        }],
      },
    });
    const correctProfile = vi.fn().mockResolvedValue(updated);
    const { wrapper } = mountCard({ correctProfile });
    await flushPromises();

    await wrapper.get('[data-testid="profile-field-learning_goals"] button').trigger("click");
    await wrapper.get('[data-testid="profile-editor-learning_goals"] textarea').setValue('{"goal":"掌握指针"}');
    const saveButton = wrapper
      .findAll('[data-testid="profile-editor-learning_goals"] button')
      .find((button) => button.text() === "保存");
    await saveButton!.trigger("click");
    await flushPromises();

    expect(correctProfile).toHaveBeenCalledWith(expect.objectContaining({
      corrections: { learning_goals: { goal: "掌握指针" } },
      expectedVersion: 3,
      csrfToken: "c".repeat(64),
    }));
    expect(wrapper.text()).toContain("版本 v4");
    expect(wrapper.find('[data-testid="profile-editor-learning_goals"]').exists()).toBe(false);
  });

  it("surfaces a version conflict and reloads the latest snapshot", async () => {
    const newer = makeProfile({ version: 9, learning_goals: { goal: "别人的修改" } });
    const fetchProfile = vi.fn()
      .mockResolvedValueOnce(sampleProfile)
      .mockResolvedValueOnce(newer);
    const correctProfile = vi.fn().mockRejectedValue(
      new ProfileRequestError({ message: "冲突", code: "PROFILE_VERSION_CONFLICT", retryable: true }),
    );
    const { wrapper } = mountCard({ fetchProfile, correctProfile });
    await flushPromises();

    await wrapper.get('[data-testid="profile-field-learning_goals"] button').trigger("click");
    await wrapper.get('[data-testid="profile-editor-learning_goals"] textarea').setValue('{"goal":"我的修改"}');
    const saveButton = wrapper
      .findAll('[data-testid="profile-editor-learning_goals"] button')
      .find((button) => button.text() === "保存");
    await saveButton!.trigger("click");
    await flushPromises();

    expect(wrapper.get('[data-testid="profile-editor-learning_goals"]').text()).toContain("重新加载");
    await wrapper.get('[data-testid="profile-editor-learning_goals"] button').trigger("click");
    await flushPromises();

    expect(fetchProfile).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("版本 v9");
  });

  it("rejects invalid JSON before sending a correction", async () => {
    const correctProfile = vi.fn();
    const { wrapper } = mountCard({ correctProfile });
    await flushPromises();

    await wrapper.get('[data-testid="profile-field-learning_goals"] button').trigger("click");
    await wrapper.get('[data-testid="profile-editor-learning_goals"] textarea').setValue("not-json");
    const saveButton = wrapper
      .findAll('[data-testid="profile-editor-learning_goals"] button')
      .find((button) => button.text() === "保存");
    await saveButton!.trigger("click");
    await flushPromises();

    expect(wrapper.get('[data-testid="profile-editor-learning_goals"]').text()).toContain("有效的 JSON");
    expect(correctProfile).not.toHaveBeenCalled();
  });
});
