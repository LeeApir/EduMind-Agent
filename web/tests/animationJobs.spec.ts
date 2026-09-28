import { describe, expect, it, vi } from "vitest";

import {
  AnimationApiError, cancelAnimationJob, loadAnimationJob, requestAnimation, retryAnimationJob,
  type AnimationJob,
} from "../src/api/animationJobs";

const queued: AnimationJob = {
  id: "job-1", learning_unit_id: "unit-1", template_id: "linked-list-insertion",
  status: "queued", attempt: 0, progress: 0, last_event_id: 1,
};

describe("animation job HTTP client", () => {
  it("uses owner cookie, CSRF and a stable key only for explicit actions", async () => {
    const fetchImpl = vi.fn(async () => Response.json(queued));
    const request = {
      template_id: "linked-list-insertion" as const, template_version: "1.0.0" as const,
      scene_version: 1, parameters: { values: [1, 3, 5], index: 1, value: 4 },
    };
    expect(await requestAnimation("unit-1", request, "csrf", "request-key", fetchImpl)).toEqual(queued);
    expect(fetchImpl).toHaveBeenCalledWith("/api/learning-units/unit-1/animations", expect.objectContaining({
      method: "POST", credentials: "same-origin",
      headers: expect.objectContaining({ "X-CSRF-Token": "csrf", "Idempotency-Key": "request-key" }),
      body: JSON.stringify(request),
    }));
    await loadAnimationJob("job-1", fetchImpl);
    expect(fetchImpl).toHaveBeenLastCalledWith("/api/animation-jobs/job-1", expect.objectContaining({
      credentials: "same-origin",
    }));
    await cancelAnimationJob("job-1", "csrf", "cancel-key", fetchImpl);
    expect(fetchImpl).toHaveBeenLastCalledWith("/api/animation-jobs/job-1/cancel", expect.objectContaining({
      method: "POST", headers: expect.objectContaining({ "Idempotency-Key": "cancel-key" }),
    }));
    await retryAnimationJob("job-1", "csrf", "retry-key", fetchImpl);
    expect(fetchImpl).toHaveBeenLastCalledWith("/api/animation-jobs/job-1/retry", expect.objectContaining({
      method: "POST", headers: expect.objectContaining({ "Idempotency-Key": "retry-key" }),
    }));
  });

  it("rejects malformed receipts and exposes stable API error codes", async () => {
    await expect(loadAnimationJob("job-1", vi.fn(async () => Response.json({ status: "queued" }))))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" });
    await expect(loadAnimationJob("job-1", vi.fn(async () => Response.json({
      code: "NOT_FOUND", message: "missing", retryable: false,
    }, { status: 404 })))).rejects.toBeInstanceOf(AnimationApiError);
  });
});
