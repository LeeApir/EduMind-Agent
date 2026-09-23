import { describe, expect, it, vi } from "vitest";

import {
  correctProfile,
  ensureProfileSession,
  fetchProfile,
  fetchProfileHistory,
  profileFieldStatus,
  strongestEvidenceSource,
  type Profile,
} from "../src/api/profile";

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

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("profile API client", () => {
  it("reads the current profile over the owner-scoped endpoint", async () => {
    const profile = makeProfile({ version: 3, professional_background: { major: "计算机" } });
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(profile));

    const result = await fetchProfile({ fetchImpl });

    expect(result).toEqual(profile);
    expect(fetchImpl).toHaveBeenCalledWith("/api/profile/me", expect.objectContaining({
      credentials: "same-origin",
    }));
  });

  it("turns a missing profile into a non-retryable NOT_FOUND error", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse({ code: "NOT_FOUND", message: "Resource not found." }, 404),
    );

    await expect(fetchProfile({ fetchImpl })).rejects.toMatchObject({
      code: "NOT_FOUND",
      retryable: false,
    });
  });

  it("maps an upstream failure to its retryable code", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse({ code: "RATE_LIMITED", message: "请稍后重试。", retryable: true }, 429),
    );

    await expect(fetchProfile({ fetchImpl })).rejects.toMatchObject({
      code: "RATE_LIMITED",
      retryable: true,
    });
  });

  it("sends a correction with CSRF, idempotency and version preconditions", async () => {
    const updated = makeProfile({ version: 2, learning_goals: { goal: "通过考试" } });
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(updated));

    const result = await correctProfile({
      corrections: { learning_goals: { goal: "通过考试" } },
      expectedVersion: 1,
      csrfToken: "c".repeat(64),
      idempotencyKey: "idempotency-key-0001",
      fetchImpl,
    });

    expect(result).toEqual(updated);
    expect(fetchImpl).toHaveBeenCalledWith("/api/profile/me", expect.objectContaining({
      method: "PATCH",
      credentials: "same-origin",
      headers: expect.objectContaining({
        "X-CSRF-Token": "c".repeat(64),
        "Idempotency-Key": "idempotency-key-0001",
        "If-Match-Profile-Version": "1",
      }),
      body: JSON.stringify({ learning_goals: { goal: "通过考试" } }),
    }));
  });

  it("surfaces a version conflict as retryable", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse({ code: "PROFILE_VERSION_CONFLICT", message: "Profile version no longer matches." }, 409),
    );

    await expect(correctProfile({
      corrections: { learning_goals: { goal: "x" } },
      expectedVersion: 1,
      csrfToken: "c".repeat(64),
      idempotencyKey: "idempotency-key-0002",
      fetchImpl,
    })).rejects.toMatchObject({ code: "PROFILE_VERSION_CONFLICT", retryable: true });
  });

  it("paginates history and preserves the next cursor", async () => {
    const page = {
      items: [makeProfile({ version: 2 }), makeProfile({ version: 1 })],
      next_before_version: 1,
    };
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(page));

    const result = await fetchProfileHistory({ limit: 2, beforeVersion: 3, fetchImpl });

    expect(result.next_before_version).toBe(1);
    expect(result.items).toHaveLength(2);
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/profile/me/history?limit=2&before_version=3",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("obtains a CSRF token, creating a guest session on first visit", async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ code: "UNAUTHORIZED", message: "unauthorized" }, 401))
      .mockResolvedValueOnce(jsonResponse({ csrf_token: "c".repeat(64) }));

    const token = await ensureProfileSession({ fetchImpl });

    expect(token).toBe("c".repeat(64));
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });
});

describe("profile field classification", () => {
  it("distinguishes unknown, inferred, known and corrected fields", () => {
    const profile = makeProfile({
      professional_background: { major: "计算机" },
      learning_goals: { goal: "掌握指针" },
      cognitive_style: { pace: "steady" },
      error_preferences: ["边界条件"],
      engineering_preference: null,
      evidence: {
        professional_background: [{
          source: "learner_statement",
          confidence: 0.9,
          observed_at: "2026-09-23T00:00:00+00:00",
          profile_version: 1,
        }],
        learning_goals: [{
          source: "manual_correction",
          confidence: 1.0,
          observed_at: "2026-09-23T00:00:00+00:00",
          profile_version: 2,
        }],
        cognitive_style: [{
          source: "learning_behavior",
          confidence: 0.7,
          observed_at: "2026-09-23T00:00:00+00:00",
          profile_version: 2,
        }],
        error_preferences: [{
          source: "explicit_feedback",
          confidence: 0.8,
          observed_at: "2026-09-23T00:00:00+00:00",
          profile_version: 1,
        }],
      },
    });

    expect(profileFieldStatus("knowledge_base", profile)).toBe("unknown");
    expect(profileFieldStatus("engineering_preference", profile)).toBe("unknown");
    expect(profileFieldStatus("professional_background", profile)).toBe("known");
    expect(profileFieldStatus("error_preferences", profile)).toBe("known");
    expect(profileFieldStatus("cognitive_style", profile)).toBe("inferred");
    expect(profileFieldStatus("learning_goals", profile)).toBe("corrected");
  });

  it("returns the strongest evidence source for a field", () => {
    const profile = makeProfile({
      learning_goals: { goal: "掌握指针" },
      evidence: {
        learning_goals: [
          {
            source: "initial_query",
            confidence: 0.5,
            observed_at: "2026-09-23T00:00:00+00:00",
            profile_version: 1,
          },
          {
            source: "manual_correction",
            confidence: 1.0,
            observed_at: "2026-09-23T00:00:00+00:00",
            profile_version: 2,
          },
        ],
      },
    });

    expect(strongestEvidenceSource("learning_goals", profile)).toBe("manual_correction");
    expect(strongestEvidenceSource("knowledge_base", profile)).toBeNull();
  });
});
